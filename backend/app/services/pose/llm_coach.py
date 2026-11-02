"""姿态周期的模型增强：Prompt 构建、结构化解析、节流与降级（工单 42）。

规则优先、模型增强：每个已完成且可评估的周期最多一次模型调用（temperature=0），
输入是**降采样后的关节角度摘要**（8–12 帧，含视角与用户动作提示，绝不含身份
信息与原始坐标序列），输出动作类型、置信度、综合质量分与一句口语化改写。

融合遵循 spec §5：规则问题主导评分——有严重（critical）问题时模型分不参与，
否则模型分只能把规则分往下压。规则问题项与规则分始终保留在响应里。

节流四层（spec §7）：每周期一次 → 同一「问题 + 动作」20 秒内不重复播报 →
单会话调用上限（用尽后转纯规则并只提示一次）→ 连续失败 3 次熔断本会话。
模型不可用（超时/限流/鉴权/不可解析/无 Key）时返回规则结果 + 模板文案，
``degraded=true`` 与稳定降级原因，HTTP 仍是 200；未熔断时下一周期继续尝试。

节流计数属于会话状态（``session_store.PoseSession.throttle`` 持有）；本模块
只做决策与调用，不保存任何跨请求数据，也不记录坐标、角度序列或身份信息。
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.ai import llm_observability as observed
from app.services.ai.llm_factory import LLMClientFactory
from app.services.pose.evaluation import (
    MAX_SCORE,
    MIN_SCORE,
    SCORE_DECIMALS,
    SEVERITY_ERROR,
    CycleEvaluation,
    Issue,
)
from app.services.pose.segmentation import (
    INDEX_LEFT_ANKLE,
    INDEX_LEFT_HIP,
    INDEX_LEFT_KNEE,
    INDEX_LEFT_SHOULDER,
    INDEX_RIGHT_ANKLE,
    INDEX_RIGHT_HIP,
    INDEX_RIGHT_KNEE,
    INDEX_RIGHT_SHOULDER,
)
from app.services.user.api_key_service import ApiKeyRequiredError

Frame = Mapping[str, Any]

# --- 节流常量（单会话维度；改动这里即可调整成本策略） -----------------------

# 单次训练会话的模型调用硬上限：量级是「数十次」，用尽后转纯规则。
MODEL_CALL_BUDGET = 20
# 连续失败多少次后熔断本会话。
BREAKER_FAILURE_THRESHOLD = 3
# 同一「问题类型 + 动作」的去重播报窗口。
REPEAT_SUPPRESS_WINDOW_MS = 20_000
# 单周期调用超时：超时就该给规则结果，不能让用户等反馈。
MODEL_TIMEOUT_SECONDS = 8.0
# 每次调用的温度：同一周期同样输入应当得到同样判断。
MODEL_TEMPERATURE = 0.0

# --- 输入最小化：帧数上限与摘要可见度 ---------------------------------------

MIN_SUMMARY_FRAMES = 8
MAX_SUMMARY_FRAMES = 12
SUMMARY_MIN_VISIBILITY = 0.3
SUMMARY_MIN_TRUNK_HEIGHT = 0.05
MAX_FEEDBACK_CHARS = 120

# --- 动作词表（跨端契约；用户手选也落在这个集合里） -------------------------

ACTION_SQUAT = "squat"
ACTION_DEADLIFT = "deadlift"
ACTION_OTHER = "other"
ACTION_TYPES = frozenset({ACTION_SQUAT, ACTION_DEADLIFT, ACTION_OTHER})

ACTION_SOURCE_LLM = "llm"
ACTION_SOURCE_USER = "user"

# 用户手选动作与模型输出都先归一化到这个表，未知一律 other。
ACTION_ALIASES = {
    ACTION_SQUAT: ACTION_SQUAT,
    "深蹲": ACTION_SQUAT,
    ACTION_DEADLIFT: ACTION_DEADLIFT,
    "硬拉": ACTION_DEADLIFT,
    ACTION_OTHER: ACTION_OTHER,
}

# 动作置信度低于该阈值时只保留 other，避免把模棱两可的识别当结论。
ACTION_CONFIDENCE_MIN = 0.4

# --- 反馈来源与降级原因（稳定码，前端据此决定文案与埋点） -------------------

FEEDBACK_LLM = "llm"
FEEDBACK_TEMPLATE = "template"

DEGRADE_NO_KEY = "api_key_unavailable"
DEGRADE_TIMEOUT = "timeout"
DEGRADE_RATE_LIMITED = "rate_limited"
DEGRADE_AUTH_FAILED = "auth_failed"
DEGRADE_UNPARSABLE = "unparsable"
# 上两个不是失败，而是节流闸门：上限用尽与熔断。
DEGRADE_BUDGET_EXHAUSTED = "budget_exhausted"
DEGRADE_CIRCUIT_OPEN = "circuit_open"
# 凭据解析/工厂自身异常：不是「没有 Key」，不能把整个会话永久降级。
DEGRADE_PROVIDER_ERROR = "provider_error"

# 供应商错误分类 → 对外降级原因（只暴露这五个稳定值）。
_DEGRADE_REASONS = {
    observed.ERROR_CATEGORY_AUTH: DEGRADE_AUTH_FAILED,
    observed.ERROR_CATEGORY_RATE_LIMIT: DEGRADE_RATE_LIMITED,
    observed.ERROR_CATEGORY_TIMEOUT: DEGRADE_TIMEOUT,
    observed.ERROR_CATEGORY_NETWORK: DEGRADE_TIMEOUT,
    observed.ERROR_CATEGORY_OUTPUT_PARSE: DEGRADE_UNPARSABLE,
    observed.ERROR_CATEGORY_UNKNOWN: DEGRADE_UNPARSABLE,
}

# 上限用尽时只提示一次；无 Key 不提示（用户可能就想用基础模式）。
BUDGET_PAUSED_NOTICE = "这次先给基础提示，深度点评已暂停。"

NO_ISSUE_KEY = "none"
NO_ACTION_KEY = "unknown"
_CATEGORY_LABEL_DIGEST_SEPARATOR = "、"

# --- 节流闸门 ---------------------------------------------------------------

GATE_OK = "ok"
GATE_KEYLESS = "keyless"
GATE_CIRCUIT_OPEN = "circuit_open"
GATE_BUDGET = "budget"


@dataclass
class ThrottleState:
    """单会话的模型节流状态：计数、上限、熔断与去重窗口。

    活在会话上（``PoseSession.throttle``），随会话过期一起丢弃；不落盘。
    """

    calls: int = 0
    degraded_cycles: int = 0
    consecutive_failures: int = 0
    circuit_open: bool = False
    keyless: bool = False
    paused_notice_sent: bool = False
    # 键是「动作:主要问题类型」，值是上次播报的时间（毫秒，会话时钟）。
    last_spoken_at_ms: dict[str, int] = field(default_factory=dict)

    @property
    def budget_exhausted(self) -> bool:
        return self.calls >= MODEL_CALL_BUDGET


def throttle_gate(state: ThrottleState) -> str:
    """判断本周期能不能调用模型：无害的早退，绝不重试。"""
    if state.keyless:
        return GATE_KEYLESS
    if state.circuit_open:
        return GATE_CIRCUIT_OPEN
    if state.calls >= MODEL_CALL_BUDGET:
        return GATE_BUDGET
    return GATE_OK


# --- 结果形状 ---------------------------------------------------------------


@dataclass(frozen=True)
class ActionGuess:
    """动作判断：name 落在 ACTION_TYPES，source 标明来源是模型还是用户。"""

    name: str
    confidence: float
    source: str = ACTION_SOURCE_LLM


@dataclass(frozen=True)
class CycleEnhancement:
    """一个周期的增强结果：最终分、动作、播报文本与降级标记。

    ``hint=None`` + ``spoken=False`` 表示命中 20 秒去重窗口：不重复播报，
    但评分照常更新；``degrade_reason`` 是稳定码，不是异常文本。
    """

    score: float | None
    action: ActionGuess | None = None
    model_score: float | None = None
    hint: str | None = None
    feedback_source: str = FEEDBACK_TEMPLATE
    spoken: bool = True
    degraded: bool = False
    degrade_reason: str | None = None
    notice: str | None = None
    called: bool = False
    # 模型补充的、规则未覆盖的观察：以 info 级问题进入反馈，不改分数段。
    info_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelInsight:
    """解析后的模型输出；分数与置信度已归一化，综合分是可选的。"""

    action: str
    confidence: float
    score: float | None
    feedback: str
    observations: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrameSummary:
    """一帧降采样摘要：只有时间与关节角度，没有坐标。"""

    t_ms: int
    knee_left: float | None
    knee_right: float | None
    trunk_lean: float | None


# --- 评分融合 ---------------------------------------------------------------


def fuse_score(
    rule_score: float,
    model_score: float | None,
    issues: Sequence[Issue],
) -> float:
    """规则问题主导评分：有严重问题钉住规则分，否则只允许模型把分往下压。"""
    if model_score is None:
        return rule_score
    if any(issue.severity == SEVERITY_ERROR for issue in issues):
        return rule_score
    return round(min(rule_score, model_score), SCORE_DECIMALS)


def normalize_action(name: object) -> str:
    """把模型输出或用户手选的动作名归一化到 ACTION_TYPES。"""
    if not isinstance(name, str):
        return ACTION_OTHER
    return ACTION_ALIASES.get(name.strip().lower(), ACTION_OTHER)


def action_from_hint(hint: str | None) -> ActionGuess | None:
    """用户手选动作优先于模型识别；没有有效提示时返回 None。"""
    if not hint or not hint.strip():
        return None
    return ActionGuess(name=normalize_action(hint), confidence=1.0, source=ACTION_SOURCE_USER)


# --- 输入最小化：关节角度摘要 -----------------------------------------------


def _visible_point(frame: Frame, index: int) -> tuple[float, float] | None:
    """取一个足够可见的关键点；低置信度/非法数值一律不参与摘要。"""
    keypoints = frame.get("keypoints") or ()
    if index < 0 or index >= len(keypoints):
        return None
    point = keypoints[index]
    try:
        x = float(point["x"])
        y = float(point["y"])
        visibility = float(point.get("visibility", 1.0))
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(visibility)):
        return None
    if visibility < SUMMARY_MIN_VISIBILITY:
        return None
    return x, y


def _joint_angle(frame: Frame, indices: tuple[int, int, int]) -> float | None:
    """三点夹角（度）；任一点不可见或退化时返回 None。"""
    first = _visible_point(frame, indices[0])
    joint = _visible_point(frame, indices[1])
    last = _visible_point(frame, indices[2])
    if first is None or joint is None or last is None:
        return None
    first_vector = (first[0] - joint[0], first[1] - joint[1])
    last_vector = (last[0] - joint[0], last[1] - joint[1])
    norm_first = math.hypot(*first_vector)
    norm_last = math.hypot(*last_vector)
    if norm_first <= 0.0 or norm_last <= 0.0:
        return None
    cosine = (
        first_vector[0] * last_vector[0] + first_vector[1] * last_vector[1]
    ) / (norm_first * norm_last)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _trunk_lean_deg(frame: Frame) -> float | None:
    """肩-髋连线与竖直方向的最大夹角；肩必须明显高于髋。"""
    angles: list[float] = []
    for shoulder_index, hip_index in (
        (INDEX_LEFT_SHOULDER, INDEX_LEFT_HIP),
        (INDEX_RIGHT_SHOULDER, INDEX_RIGHT_HIP),
    ):
        shoulder = _visible_point(frame, shoulder_index)
        hip = _visible_point(frame, hip_index)
        if shoulder is None or hip is None:
            continue
        height = hip[1] - shoulder[1]
        if height <= SUMMARY_MIN_TRUNK_HEIGHT:
            continue
        angles.append(math.degrees(math.atan2(abs(shoulder[0] - hip[0]), height)))
    return max(angles) if angles else None


def _round_angle(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _frame_t_ms(frame: Frame) -> int:
    try:
        return int(frame.get("t_ms", 0))
    except (TypeError, ValueError):
        return 0


def summarize_frames(
    frames: Sequence[Frame],
    *,
    max_frames: int = MAX_SUMMARY_FRAMES,
) -> tuple[FrameSummary, ...]:
    """把周期窗口等距降采样成 ≤12 帧的关节角度摘要（绝不带坐标）。"""
    total = len(frames)
    if total == 0:
        return ()
    count = min(max_frames, total)
    if count == 1:
        indices = [0]
    else:
        indices = sorted({round(index * (total - 1) / (count - 1)) for index in range(count)})
    summaries: list[FrameSummary] = []
    for index in indices:
        frame = frames[index]
        summaries.append(
            FrameSummary(
                t_ms=_frame_t_ms(frame),
                knee_left=_round_angle(
                    _joint_angle(frame, (INDEX_LEFT_HIP, INDEX_LEFT_KNEE, INDEX_LEFT_ANKLE))
                ),
                knee_right=_round_angle(
                    _joint_angle(frame, (INDEX_RIGHT_HIP, INDEX_RIGHT_KNEE, INDEX_RIGHT_ANKLE))
                ),
                trunk_lean=_round_angle(_trunk_lean_deg(frame)),
            )
        )
    return tuple(summaries)


def _format_angle(value: float | None) -> str:
    return "null" if value is None else f"{value:.1f}"


def _format_summary_line(summary: FrameSummary) -> str:
    return (
        f"t={summary.t_ms} knee_left={_format_angle(summary.knee_left)}"
        f" knee_right={_format_angle(summary.knee_right)}"
        f" trunk_lean={_format_angle(summary.trunk_lean)}"
    )


def _issue_digest(issues: Sequence[Issue]) -> str:
    if not issues:
        return NO_ISSUE_KEY
    return _CATEGORY_LABEL_DIGEST_SEPARATOR.join(
        f"{issue.type}({issue.severity})" for issue in issues
    )


# --- Prompt -----------------------------------------------------------------

COACH_SYSTEM_PROMPT = """你是西海岸风格的健身教练，说话像街头健身房的 bro。
输出要求：
- 中文为主，每句话最多 1–2 个英文词（yo、bro、homie、let's go、good job 之类）
- 只讲动作层面的事实与改法，绝不提伤病、诊断、关节结构或医疗建议
- 不用「您」，不说教，反馈不超过 40 个字
- 只输出一个 JSON 对象，不要代码围栏，不要解释文字：
{
  "action": "squat|deadlift|other",
  "action_confidence": 0-1,
  "quality_score": 0-10,
  "feedback": "一句口语化提示"
}
"""


def build_prompt(
    *,
    frames: Sequence[Frame],
    evaluation: CycleEvaluation,
    camera_view: str,
    exercise_hint: str | None = None,
) -> list[Any]:
    """构建一次调用的消息：只有聚合摘要、视角与规则命中，没有身份与坐标。"""
    summaries = summarize_frames(frames)
    lines = [f"机位：{camera_view}"]
    if exercise_hint and exercise_hint.strip():
        lines.append(f"用户指定动作：{exercise_hint.strip()}")
    lines.append(f"规则命中：{_issue_digest(evaluation.issues)}")
    lines.append(f"角度摘要（单位：度，null 表示该点不可见，共 {len(summaries)} 帧）：")
    lines.extend(_format_summary_line(summary) for summary in summaries)
    lines.append("请只输出 JSON。")
    return [
        SystemMessage(content=COACH_SYSTEM_PROMPT),
        HumanMessage(content="\n".join(lines)),
    ]


# --- 输出解析 ---------------------------------------------------------------


def _decode_payload(text: str) -> dict[str, Any] | None:
    """从模型输出里取一个 JSON 对象；容忍代码围栏与前后缀文字。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    start = stripped.find("{")
    if start < 0:
        return None
    try:
        payload, _consumed = json.JSONDecoder().raw_decode(stripped[start:])
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if not isinstance(value, str):
            return None
        try:
            value = float(value)
        except ValueError:
            return None
    number = float(value)
    return number if math.isfinite(number) else None


def parse_model_output(text: str) -> ModelInsight | None:
    """解析并归一化模型输出；任何不合规都返回 None（按不可解析降级）。

    综合质量分是可选的：缺失或非法时保留动作与文案，最终分退回规则分，
    不因为一个可选字段把整次增强判死。
    """
    payload = _decode_payload(text or "")
    if payload is None:
        return None
    feedback = payload.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        return None
    confidence = _as_float(payload.get("action_confidence"))
    if confidence is None:
        return None
    score = _as_float(payload.get("quality_score"))
    if score is not None:
        score = round(min(MAX_SCORE, max(MIN_SCORE, score)), SCORE_DECIMALS)
    action = normalize_action(payload.get("action"))
    if confidence < ACTION_CONFIDENCE_MIN:
        action = ACTION_OTHER
    observations = tuple(
        str(item).strip()[:MAX_FEEDBACK_CHARS]
        for item in (payload.get("observations") or [])
        if isinstance(item, str) and item.strip()
    )
    return ModelInsight(
        action=action,
        confidence=round(min(1.0, max(0.0, confidence)), 2),
        score=score,
        feedback=feedback.strip()[:MAX_FEEDBACK_CHARS],
        observations=observations[:3],
    )


# --- 节流状态迁移 -----------------------------------------------------------


def _primary_issue_key(evaluation: CycleEvaluation) -> str:
    return evaluation.issues[0].type if evaluation.issues else NO_ISSUE_KEY


def speak_once(
    state: ThrottleState | None,
    *,
    action: ActionGuess | None,
    evaluation: CycleEvaluation,
    hint: str | None,
    now_ms: int,
) -> tuple[str | None, bool]:
    """20 秒去重：同一「问题 + 动作」不重复播报；返回 (播报文本, 是否播报)。

    没有动作标识时无法建立去重键（降级路径不认识动作），模板文案照常播报。
    """
    if not hint:
        return None, True
    if state is None:
        return hint, True
    # 没有动作标识时（降级 / 无 Key / 模型没给出动作）仍按问题类型去重，
    # 否则纯规则会话会把同一句模板提示每个周期重复念一遍。
    action_key = action.name if action is not None else NO_ACTION_KEY
    key = f"{action_key}:{_primary_issue_key(evaluation)}"
    last = state.last_spoken_at_ms.get(key)
    if last is not None and now_ms - last < REPEAT_SUPPRESS_WINDOW_MS:
        return None, False
    state.last_spoken_at_ms[key] = now_ms
    return hint, True


def rule_only_enhancement(
    evaluation: CycleEvaluation,
    *,
    action: ActionGuess | None = None,
    state: ThrottleState | None = None,
    now_ms: int = 0,
    degraded: bool = False,
    degrade_reason: str | None = None,
    notice: str | None = None,
) -> CycleEnhancement:
    """纯规则结果 + 模板文案（无模型 / 上限用尽 / 熔断 / 无 Key 共用）。"""
    hint, spoken = speak_once(
        state, action=action, evaluation=evaluation, hint=evaluation.hint, now_ms=now_ms
    )
    return CycleEnhancement(
        score=evaluation.score,
        action=action,
        hint=hint,
        feedback_source=FEEDBACK_TEMPLATE,
        spoken=spoken,
        degraded=degraded,
        degrade_reason=degrade_reason,
        notice=notice,
    )


class PoseLLMCoach:
    """一个训练会话的模型增强执行体：每次请求按需构造，不持有会话状态。"""

    def __init__(
        self,
        *,
        user_id: int | None = None,
        db: Any = None,
        factory: LLMClientFactory | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.user_id = user_id
        self._factory = factory or LLMClientFactory(db)
        # None 表示按模块常量取，便于运行期调整与测试注入。
        self.timeout_seconds = timeout_seconds

    @property
    def timeout(self) -> float:
        return MODEL_TIMEOUT_SECONDS if self.timeout_seconds is None else self.timeout_seconds

    async def enhance(
        self,
        *,
        frames: Sequence[Frame],
        evaluation: CycleEvaluation,
        camera_view: str,
        exercise_hint: str | None = None,
        state: ThrottleState,
        now_ms: int = 0,
    ) -> CycleEnhancement:
        """增强一个周期：节流闸门 → 一次调用 → 解析 → 融合；失败即降级。"""
        hint_action = action_from_hint(exercise_hint)
        gate = throttle_gate(state)
        if gate != GATE_OK:
            return self._gate_result(gate, evaluation, hint_action, state, now_ms)

        messages = build_prompt(
            frames=frames,
            evaluation=evaluation,
            camera_view=camera_view,
            exercise_hint=exercise_hint,
        )
        try:
            client = await self._factory.get_client(
                user_id=self.user_id, model_type="chat"
            )
        except ApiKeyRequiredError:
            # 无 Key 且系统回退关闭：整个会话纯规则，不提示配置 Key。
            return self._keyless_result(evaluation, hint_action, state, now_ms)
        except Exception:
            # 凭据解析/工厂自身异常不是「没有 Key」：本周期按 provider_error 降级，
            # 并计入连续失败；下一周期仍会重试，绝不永久改写会话状态。
            return self._failure_result(
                evaluation,
                hint_action,
                state,
                now_ms,
                DEGRADE_PROVIDER_ERROR,
            )

        _apply_temperature(client)
        state.calls += 1
        try:
            response = await asyncio.wait_for(
                observed.invoke(client, messages, purpose=observed.PURPOSE_CHAT),
                timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - 所有失败都要转成稳定降级原因
            # LLMCallError 已经由观测层记过 failed 事件；本层自己截断的超时没有，
            # 需要补一条降级事件，保证「看到了失败」和「用户被降级」都可观测。
            already_logged = getattr(exc, "category", None) is not None
            return self._failure_result(
                evaluation,
                hint_action,
                state,
                now_ms,
                _degrade_reason_for(exc),
                client=client,
                observed_already=already_logged,
            )

        insight = parse_model_output(getattr(response, "content", "") or "")
        if insight is None:
            observed.degraded(
                client, purpose=observed.PURPOSE_CHAT, reason=DEGRADE_UNPARSABLE
            )
            return self._failure_result(
                evaluation,
                hint_action,
                state,
                now_ms,
                DEGRADE_UNPARSABLE,
                client=client,
                observed_already=True,
            )

        state.consecutive_failures = 0
        action = hint_action or ActionGuess(
            name=insight.action,
            confidence=insight.confidence,
            source=ACTION_SOURCE_LLM,
        )
        hint, spoken = speak_once(
            state,
            action=action,
            evaluation=evaluation,
            hint=insight.feedback,
            now_ms=now_ms,
        )
        return CycleEnhancement(
            score=fuse_score(evaluation.score, insight.score, evaluation.issues),
            action=action,
            model_score=insight.score,
            hint=hint,
            feedback_source=FEEDBACK_LLM,
            spoken=spoken,
            called=True,
            info_issues=insight.observations,
        )

    # --- 闸门与降级 -------------------------------------------------------

    def _gate_result(
        self,
        gate: str,
        evaluation: CycleEvaluation,
        action: ActionGuess | None,
        state: ThrottleState,
        now_ms: int,
    ) -> CycleEnhancement:
        """闸门关闭时的纯规则结果；上限用尽只提示一次。"""
        notice = None
        if gate == GATE_KEYLESS:
            reason = DEGRADE_NO_KEY
        elif gate == GATE_CIRCUIT_OPEN:
            reason = DEGRADE_CIRCUIT_OPEN
        else:
            reason = DEGRADE_BUDGET_EXHAUSTED
            if not state.paused_notice_sent:
                state.paused_notice_sent = True
                notice = BUDGET_PAUSED_NOTICE
        state.degraded_cycles += 1
        return rule_only_enhancement(
            evaluation,
            action=action,
            state=state,
            now_ms=now_ms,
            degraded=True,
            degrade_reason=reason,
            notice=notice,
        )

    def _keyless_result(
        self,
        evaluation: CycleEvaluation,
        action: ActionGuess | None,
        state: ThrottleState,
        now_ms: int,
    ) -> CycleEnhancement:
        """无 Key：本会话永久转纯规则，零调用、无凭据引导文案。"""
        first_keyless = not state.keyless
        state.keyless = True
        state.degraded_cycles += 1
        if first_keyless:
            # 整个会话只记一次：继续每个周期打警告只会制造噪声。
            observed.degraded(
                observed.ClientProvenance(dependency="none", llm_mode="none"),
                purpose=observed.PURPOSE_CHAT,
                reason=DEGRADE_NO_KEY,
            )
        return rule_only_enhancement(
            evaluation,
            action=action,
            state=state,
            now_ms=now_ms,
            degraded=True,
            degrade_reason=DEGRADE_NO_KEY,
        )

    def _failure_result(
        self,
        evaluation: CycleEvaluation,
        action: ActionGuess | None,
        state: ThrottleState,
        now_ms: int,
        reason: str,
        *,
        client: Any = None,
        observed_already: bool = False,
    ) -> CycleEnhancement:
        """失败：累计连续失败、必要时熔断，本周期返回规则结果 + 模板文案。"""
        state.degraded_cycles += 1
        state.consecutive_failures += 1
        if state.consecutive_failures >= BREAKER_FAILURE_THRESHOLD:
            state.circuit_open = True
        if not observed_already:
            observed.degraded(
                client if client is not None else observed.ClientProvenance(),
                purpose=observed.PURPOSE_CHAT,
                reason=reason,
            )
        return rule_only_enhancement(
            evaluation,
            action=action,
            state=state,
            now_ms=now_ms,
            degraded=True,
            degrade_reason=reason,
        )


def _apply_temperature(client: Any) -> None:
    """按调用点固定温度（工厂只负责凭据与模型选择）；不支持改参数的替身保持原样。"""
    try:
        client.temperature = MODEL_TEMPERATURE
    except (AttributeError, TypeError, ValueError):
        pass


def _degrade_reason_for(exc: BaseException) -> str:
    """把一次调用失败映射成稳定降级原因；不读取异常文本。"""
    category = getattr(exc, "category", None)
    if category is None:
        category = observed.error_category(exc)
    return _DEGRADE_REASONS.get(category, DEGRADE_UNPARSABLE)
