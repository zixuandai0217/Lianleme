"""两路 LLM 分析器（伤病风险 / 体重体脂趋势）与完整降级路径（工单 25）。

模型可用时返回结构化健康评分（0-10，10 最好、0 最差）并进入五维合并；超时、
限流、鉴权失败、输出不可解析、缺少可用 Key 时，只把该维降级成规则近似分与
模板理由，其余维度与决策方向保持不变。

隐私边界：送进 Prompt 的只有聚合摘要（均值、趋势方向、记录数、训练天数、
规则维度分数），绝不发送用户标识、邮箱、昵称、照片或逐日原始序列。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage

from app.services.ai import llm_observability as observed
from app.services.ai.adjust_analyzers import (
    COMPLETENESS_DEFAULT,
    COMPLETENESS_FULL,
    COMPLETENESS_PARTIAL,
    DEGRADATION_INSUFFICIENT_DATA,
    DEGRADATION_NOTE,
    DIMENSION_INJURY_RISK,
    LLM_DIMENSIONS,
    SOURCE_LLM,
    AnalyzerResult,
)
from app.services.user.api_key_service import ApiKeyRequiredError

# 单路超时预算：ADR-0003 要求个位数秒；超时即降级，不重试。
LLM_ANALYZER_TIMEOUT_SECONDS = 8.0
# 温度固定 0：同一输入得到稳定评分，重试的边际价值低（ADR-0003）。
LLM_ANALYZER_TEMPERATURE = 0

# 稳定降级原因分类：只进日志与合并元数据，不作为用户可见文案。
DEGRADATION_NO_KEY = "no_available_key"
DEGRADATION_TIMEOUT = "timeout"
DEGRADATION_RATE_LIMIT = "rate_limit"
DEGRADATION_AUTH = "auth_failed"
DEGRADATION_OUTPUT_UNPARSEABLE = "output_unparseable"
DEGRADATION_PROVIDER_ERROR = "provider_error"
DEGRADATION_UNEXPECTED = "unexpected_error"

# 目标方向：档案里的中文目标值（schemas.user.UserProfile）。
GOAL_CUT = "减脂"
GOAL_BULK = "增肌"
GOAL_MAINTAIN = ("塑形", "提升体能")

# 规则近似阈值：只用于降级展示，不参与方向判定。
INJURY_BASE_SCORE = 9.0
INJURY_LOW_COMPLETION = 0.7
INJURY_VERY_LOW_COMPLETION = 0.5
INJURY_HIGH_FATIGUE = 3.5
INJURY_VERY_HIGH_FATIGUE = 4.5
INJURY_MANY_CONSECUTIVE_DAYS = 4
INJURY_TOO_MANY_CONSECUTIVE_DAYS = 6
BODY_ALIGNED_SCORE = 8.0
BODY_NEUTRAL_SCORE = 5.0
BODY_CONFLICT_SCORE = 4.0
BODY_FLAT_EPSILON_KG = 0.1

# 模板文案：不包含供应商原文、凭据错误码或「请配置 API Key」引导。
INJURY_DEGRADED_REASON = (
    f"{DEGRADATION_NOTE}，伤病风险按完成率、疲劳与连续训练天数近似评估"
)
BODY_DEGRADED_REASON = (
    f"{DEGRADATION_NOTE}，体重趋势按记录均值、方向与次数近似评估"
)
BODY_INSUFFICIENT_REASON = (
    f"{DEGRADATION_NOTE}，体重记录不足 2 条，体成分按中性分占位"
)
INJURY_SUGGESTION = "先别急着加码，joints 舒服了再上强度，恢复到位才是真的稳"
BODY_SUGGESTION = "按当前目标继续观察体重趋势，暂不改动计划"

_INJURY_INSTRUCTION = """你正在评估训练计划调整中的「伤病风险」维度。
请只根据下面的聚合摘要输出严格 JSON，不要输出 Markdown 或代码块：
{"score": <0-10 的健康评分>, "reason": "<一句话依据>", "suggestion": "<一条调整建议>"}
分数是健康评分：10 表示风险最低、状态最好，0 表示风险最高。不要复述用户的具体伤病细节。"""

_BODY_INSTRUCTION = """你正在评估训练计划调整中的「体重/体脂趋势」维度。
请只根据下面的聚合摘要输出严格 JSON，不要输出 Markdown 或代码块：
{"score": <0-10 的健康评分>, "reason": "<一句话依据>", "suggestion": "<一条调整建议>"}
分数是健康评分：10 表示趋势与目标最一致，0 表示最背离目标。不要复述用户的逐日体重数值。"""

_PROMPT_HEADER = "聚合摘要（JSON）："


@dataclass(frozen=True)
class LlmAnalyzerContext:
    """模型维度的运行上下文：客户端、聚合摘要与不可用原因。"""

    client: Any = None
    summary: Mapping[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None


class _ZeroTemperatureClient:
    """把 temperature=0 固化在调用边界，同时保留供应商来源供观测日志使用。"""

    def __init__(self, client: Any):
        self._client = client
        self.llm_provider = getattr(client, "llm_provider", "unknown")
        self.llm_mode = getattr(client, "llm_mode", "unknown")

    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        return await self._client.ainvoke(
            messages,
            temperature=LLM_ANALYZER_TEMPERATURE,
            **kwargs,
        )


async def resolve_llm_context(
    factory: Any,
    user_id: int,
    *,
    summary: Mapping[str, Any] | None = None,
) -> LlmAnalyzerContext:
    """解析用户模型客户端；无 Key 或解析失败时返回可降级的上下文，不泄露原因文本。"""
    resolved = dict(summary or {})
    try:
        client = await factory.get_client(user_id=user_id, model_type="chat")
    except ApiKeyRequiredError:
        return LlmAnalyzerContext(
            client=None,
            summary=resolved,
            unavailable_reason=DEGRADATION_NO_KEY,
        )
    except Exception:  # noqa: BLE001 - 凭据解析失败也必须降级而不是丢评估
        return LlmAnalyzerContext(
            client=None,
            summary=resolved,
            unavailable_reason=DEGRADATION_PROVIDER_ERROR,
        )
    return LlmAnalyzerContext(client=client, summary=resolved)


async def analyze_llm_dimension(
    name: str,
    payload: Mapping[str, Any],
    context: LlmAnalyzerContext | None,
) -> AnalyzerResult:
    """执行单路模型分析；任何失败都收敛成该维自己的降级结果。"""
    if name not in LLM_DIMENSIONS:
        raise ValueError(f"不是模型分析维度：{name}")

    summary = dict(context.summary) if context is not None else {}
    if context is None or context.client is None or context.unavailable_reason:
        reason = (
            context.unavailable_reason
            if context is not None and context.unavailable_reason
            else DEGRADATION_NO_KEY
        )
        return _degraded_result(name, payload, summary, reason)
    if not _has_usable_inputs(name, payload, summary):
        return _degraded_result(
            name, payload, summary, DEGRADATION_INSUFFICIENT_DATA
        )

    prompt = build_prompt(name, payload, summary)
    try:
        response = await asyncio.wait_for(
            observed.invoke(
                _ZeroTemperatureClient(context.client),
                [HumanMessage(content=prompt)],
            ),
            timeout=LLM_ANALYZER_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, TimeoutError):
        return _degraded_result(name, payload, summary, DEGRADATION_TIMEOUT)
    except observed.LLMCallError as exc:
        return _degraded_result(
            name, payload, summary, _degradation_reason_for_category(exc.category)
        )
    except Exception:  # noqa: BLE001 - 单路失败隔离是并行编排的硬要求
        return _degraded_result(name, payload, summary, DEGRADATION_UNEXPECTED)

    parsed = _parse_response(response)
    if parsed is None:
        observed.degraded(context.client, reason=observed.DEGRADED_OUTPUT_UNPARSEABLE)
        return _degraded_result(
            name, payload, summary, DEGRADATION_OUTPUT_UNPARSEABLE
        )

    score, reason, suggestion = parsed
    return AnalyzerResult(
        name=name,
        score=score,
        reason=reason,
        suggestion=suggestion,
        source=SOURCE_LLM,
        degraded=False,
        data_completeness=_success_completeness(name, payload, summary),
    )


def build_prompt(
    name: str,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> str:
    """按白名单构造 Prompt：只有聚合摘要，原始逐日序列与身份字段不会出现。"""
    instruction = (
        _INJURY_INSTRUCTION
        if name == DIMENSION_INJURY_RISK
        else _BODY_INSTRUCTION
    )
    facts = _prompt_facts(name, payload, summary)
    return (
        f"{instruction}\n\n{_PROMPT_HEADER}\n"
        f"{json.dumps(facts, ensure_ascii=False, sort_keys=True)}"
    )


def _prompt_facts(
    name: str,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """只挑白名单字段；缺失值不输出，避免把 None 伪装成真实数据。"""
    training = _mapping(summary.get("training"))
    weight = _mapping(summary.get("weight"))
    facts: dict[str, Any] = {
        "dimension": name,
        "goal": _text(summary.get("goal")),
        "height_cm": _number(summary.get("height_cm")),
        "weight_kg": _number(summary.get("weight_kg")),
        "age_band": _text(summary.get("age_band")),
        "weekly_completion_average": _number(
            summary.get("weekly_completion_average")
        ),
        "completion_average": _average(payload.get("completion_rates")),
        "completion_sample_count": _count(payload.get("completion_rates")),
        "fatigue_average": _average(payload.get("fatigue_scores")),
        "sleep_hours": _number(payload.get("sleep_hours")),
        "sleep_quality": _number(payload.get("sleep_quality")),
        "training_days": _integer(training.get("training_days")),
        "consecutive_training_days": _integer(
            training.get("consecutive_training_days")
        ),
        "weight_mean_kg": _number(weight.get("mean_kg")),
        "weight_trend": _text(weight.get("trend_direction")),
        "weight_record_count": _integer(weight.get("record_count")),
        "rule_scores": _rule_scores(summary.get("rule_scores")),
    }
    return {
        key: value
        for key, value in facts.items()
        if value is not None and value != {}
    }


def _degraded_result(
    name: str,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    degradation_reason: str,
) -> AnalyzerResult:
    """降级输出：规则近似分 + 模板理由，标记 default 以便 Merge 剔除权重。"""
    if name == DIMENSION_INJURY_RISK:
        score = approximate_injury_risk(payload, summary)
        reason = INJURY_DEGRADED_REASON
    else:
        score = approximate_body_composition(summary)
        reason = (
            BODY_INSUFFICIENT_REASON
            if degradation_reason == DEGRADATION_INSUFFICIENT_DATA
            else BODY_DEGRADED_REASON
        )
    return AnalyzerResult(
        name=name,
        score=score,
        reason=reason,
        suggestion=INJURY_SUGGESTION if name == DIMENSION_INJURY_RISK else BODY_SUGGESTION,
        source=SOURCE_LLM,
        degraded=True,
        data_completeness=COMPLETENESS_DEFAULT,
        degradation_reason=degradation_reason,
    )


def approximate_injury_risk(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> float:
    """规则近似：完成率低、疲劳高、连续训练天数多都降低健康评分。"""
    score = INJURY_BASE_SCORE
    completion = _average(payload.get("completion_rates"))
    if completion is not None:
        if completion < INJURY_VERY_LOW_COMPLETION:
            score -= 4
        elif completion < INJURY_LOW_COMPLETION:
            score -= 2
        elif completion < 0.85:
            score -= 1

    fatigue = _average(payload.get("fatigue_scores"))
    if fatigue is not None:
        if fatigue >= INJURY_VERY_HIGH_FATIGUE:
            score -= 3
        elif fatigue >= INJURY_HIGH_FATIGUE:
            score -= 2
        elif fatigue >= 2.5:
            score -= 1

    training = _mapping(summary.get("training"))
    consecutive = _integer(training.get("consecutive_training_days")) or 0
    if consecutive >= INJURY_TOO_MANY_CONSECUTIVE_DAYS:
        score -= 2
    elif consecutive >= INJURY_MANY_CONSECUTIVE_DAYS:
        score -= 1
    return _clamp_score(score)


def approximate_body_composition(summary: Mapping[str, Any]) -> float:
    """规则近似：按体重趋势与档案目标是否一致给出健康评分。"""
    weight = _mapping(summary.get("weight"))
    count = _integer(weight.get("record_count")) or 0
    trend = _text(weight.get("trend_direction"))
    if count < 2 or trend in (None, "insufficient"):
        return BODY_NEUTRAL_SCORE

    goal = _text(summary.get("goal"))
    if goal == GOAL_CUT:
        return BODY_ALIGNED_SCORE if trend == "down" else BODY_CONFLICT_SCORE
    if goal == GOAL_BULK:
        return BODY_ALIGNED_SCORE if trend == "up" else BODY_CONFLICT_SCORE
    if goal in GOAL_MAINTAIN:
        return (
            BODY_ALIGNED_SCORE
            if trend == "flat"
            else BODY_NEUTRAL_SCORE
        )
    return BODY_NEUTRAL_SCORE


def _has_usable_inputs(
    name: str,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> bool:
    if name == DIMENSION_INJURY_RISK:
        return _average(payload.get("completion_rates")) is not None
    weight = _mapping(summary.get("weight"))
    count = _integer(weight.get("record_count")) or 0
    return count >= 2


def _success_completeness(
    name: str,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> str:
    if name == DIMENSION_INJURY_RISK:
        has_completion = _average(payload.get("completion_rates")) is not None
        has_fatigue = _average(payload.get("fatigue_scores")) is not None
        training = _mapping(summary.get("training"))
        has_training = _integer(training.get("training_days")) is not None
        return (
            COMPLETENESS_FULL
            if has_completion and has_fatigue and has_training
            else COMPLETENESS_PARTIAL
        )
    weight = _mapping(summary.get("weight"))
    count = _integer(weight.get("record_count")) or 0
    trend = _text(weight.get("trend_direction"))
    return (
        COMPLETENESS_FULL
        if count >= 3 and trend not in (None, "insufficient")
        else COMPLETENESS_PARTIAL
    )


def _parse_response(response: Any) -> tuple[float, str, str] | None:
    """解析严格 JSON；Markdown 包裹可容忍，缺字段或越界一律视为不可解析。"""
    text = _response_text(response)
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    raw_score = payload.get("score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        return None
    score = float(raw_score)
    if not 0 <= score <= 10:
        return None

    reason = str(payload.get("reason") or "").strip()
    suggestion = str(payload.get("suggestion") or "").strip()
    if not reason or not suggestion:
        return None
    return score, reason, suggestion


def _response_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts)
    return str(content or "")


def _degradation_reason_for_category(category: str) -> str:
    mapping = {
        observed.ERROR_CATEGORY_TIMEOUT: DEGRADATION_TIMEOUT,
        observed.ERROR_CATEGORY_RATE_LIMIT: DEGRADATION_RATE_LIMIT,
        observed.ERROR_CATEGORY_AUTH: DEGRADATION_AUTH,
        observed.ERROR_CATEGORY_OUTPUT_PARSE: DEGRADATION_OUTPUT_UNPARSEABLE,
    }
    return mapping.get(category, DEGRADATION_PROVIDER_ERROR)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 4)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    return None


def _average(value: Any) -> float | None:
    numbers = [
        float(item)
        for item in _values(value)
        if isinstance(item, (int, float)) and not isinstance(item, bool)
    ]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 4)


def _count(value: Any) -> int | None:
    values = _values(value)
    return len(values) if values else None


def _rule_scores(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    scores = {
        str(name): round(float(score), 2)
        for name, score in value.items()
        if isinstance(score, (int, float)) and not isinstance(score, bool)
    }
    return scores


def _clamp_score(score: float) -> float:
    return max(0.0, min(10.0, round(score, 1)))
