"""HITL interrupt 判定与三选一载荷（工单 27）。

判定是**纯函数**：输入是工单 24 的评估结果（五维明细 + 合并小结）与最近几次
已落地作业的声明幅度，不读数据库、不看当前时间，所以三个触发条件可以在单元
测试里逐个覆盖。ADR-0004 的三个条件在这里收敛成稳定的 reason code：

- ``injury_risk_high``：伤病维度健康评分 ≤3（数据缺省时的中性占位不算命中）；
- ``frequent_large_adjustment``：最近 3 次已落地调整的 |幅度| 都严格 >20%；
- ``goal_conflict``：合并红标志里出现目标冲突码。

命中只决定「挂起等用户拍板」，不决定最终幅度：选项固定三档（降低强度 / 保持 /
小幅加量），首个是推荐（保守）项。用户 5 分钟不选时由服务层按推荐项代为落地，
因此这里的 ``INTERRUPT_TTL_SECONDS`` 是超时窗口的唯一常量（配置不改，避免与
其它批次争抢 ``core/config.py``）。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.models.adjustment_job import CHOSEN_BY_TIMEOUT_DEFAULT, CHOSEN_BY_USER

# 超时窗口（ADR-0004：5 分钟）。服务层的延迟任务与惰性收敛共用这个常量。
INTERRUPT_TTL_SECONDS = 300

REASON_INJURY_RISK = "injury_risk_high"
REASON_FREQUENT_LARGE = "frequent_large_adjustment"
REASON_GOAL_CONFLICT = "goal_conflict"

INJURY_RISK_SCORE_THRESHOLD = 3.0
FREQUENT_ADJUSTMENT_WINDOW = 3
FREQUENT_ADJUSTMENT_DELTA_THRESHOLD = 20.0
GOAL_CONFLICT_CODES = frozenset({"goal_conflict"})

DIRECTION_INCREASE = "increase"
DIRECTION_DECREASE = "decrease"
DIRECTION_KEEP = "keep"

OPTION_REDUCE_INTENSITY = "reduce_intensity"
OPTION_KEEP_CURRENT = "keep_current"
OPTION_INCREASE_GRADUALLY = "increase_gradually"

@dataclass(frozen=True)
class InterruptOption:
    """三选一中的一个选项：方向 + 声明幅度 + 是否推荐（保守项）。"""

    id: str
    label: str
    description: str
    direction: str
    magnitude_percent: float
    recommended: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "direction": self.direction,
            "magnitude_percent": float(self.magnitude_percent),
            "recommended": bool(self.recommended),
        }


# 选项语义固定（ADR-0004）：降低强度（推荐）、知情保持、小幅加量。
# 幅度沿用 spec 的声明区间：减量 15-20% 取下沿 15%（×0.85），加量取 5%（×1.05）。
__all__ = ["CHOSEN_BY_USER", "CHOSEN_BY_TIMEOUT_DEFAULT"]

INTERRUPT_OPTIONS: tuple[InterruptOption, ...] = (
    InterruptOption(
        id=OPTION_REDUCE_INTENSITY,
        label="降低强度（推荐）",
        description="训练难度下调 15%，先把恢复放在第一位",
        direction=DIRECTION_DECREASE,
        magnitude_percent=15.0,
        recommended=True,
    ),
    InterruptOption(
        id=OPTION_KEEP_CURRENT,
        label="保持当前计划",
        description="本周不做改动，按现在的强度继续",
        direction=DIRECTION_KEEP,
        magnitude_percent=0.0,
        recommended=False,
    ),
    InterruptOption(
        id=OPTION_INCREASE_GRADUALLY,
        label="小幅加量",
        description="训练难度上调 5%，循序渐进地推进",
        direction=DIRECTION_INCREASE,
        magnitude_percent=5.0,
        recommended=False,
    ),
)

_OPTIONS_BY_ID = {option.id: option for option in INTERRUPT_OPTIONS}


@dataclass(frozen=True)
class InterruptSignal:
    """判定结果：没有 reason code 就是不中断（正常自动落地）。"""

    reason_codes: tuple[str, ...] = ()
    summary: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def triggered(self) -> bool:
        return bool(self.reason_codes)


def _score(entry: Mapping[str, Any]) -> float | None:
    value = entry.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _recent_deltas(recent_deltas: Sequence[float]) -> list[float]:
    """服务层按「最近优先」传入；只取最近 3 次，非数值视为无法判定。"""
    window: list[float] = []
    for raw in list(recent_deltas)[:FREQUENT_ADJUSTMENT_WINDOW]:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return []
        window.append(abs(float(raw)))
    return window


def _injury_hit(dimensions: Sequence[Mapping[str, Any]]) -> float | None:
    for entry in dimensions:
        if not isinstance(entry, Mapping) or entry.get("name") != "injury_risk":
            continue
        # 缺省占位（没有真实数据）不是风险信号，避免拿中性分误触发中断。
        if entry.get("data_completeness") == "default":
            return None
        score = _score(entry)
        if score is not None and score <= INJURY_RISK_SCORE_THRESHOLD:
            return score
        return None
    return None


def detect_interrupt(
    *,
    dimensions: Sequence[Mapping[str, Any]],
    merged: Mapping[str, Any],
    recent_deltas: Sequence[float],
) -> InterruptSignal:
    """三个红标志的一票判断；命中即返回全部命中的 reason code 与证据。"""
    reasons: list[str] = []
    evidence: dict[str, Any] = {}

    injury_score = _injury_hit(dimensions)
    if injury_score is not None:
        reasons.append(REASON_INJURY_RISK)
        evidence["injury_score"] = injury_score

    deltas = _recent_deltas(recent_deltas)
    if len(deltas) >= FREQUENT_ADJUSTMENT_WINDOW and all(
        delta > FREQUENT_ADJUSTMENT_DELTA_THRESHOLD for delta in deltas
    ):
        reasons.append(REASON_FREQUENT_LARGE)
        evidence["recent_deltas"] = deltas

    red_flags = merged.get("red_flags")
    goal_flags = [
        dict(flag)
        for flag in (red_flags if isinstance(red_flags, list) else [])
        if isinstance(flag, Mapping) and flag.get("code") in GOAL_CONFLICT_CODES
    ]
    if goal_flags:
        reasons.append(REASON_GOAL_CONFLICT)
        evidence["red_flags"] = goal_flags

    overall = merged.get("overall_score")
    if isinstance(overall, (int, float)) and not isinstance(overall, bool):
        evidence["overall_score"] = float(overall)

    if not reasons:
        return InterruptSignal()
    return InterruptSignal(
        reason_codes=tuple(reasons),
        summary=_summary(reasons, evidence),
        evidence=evidence,
    )


def _summary(reasons: Sequence[str], evidence: Mapping[str, Any]) -> str:
    parts: list[str] = []
    if REASON_INJURY_RISK in reasons:
        parts.append(
            f"伤病风险维度健康评分 {evidence['injury_score']:.1f}（≤3 视为高风险）"
        )
    if REASON_FREQUENT_LARGE in reasons:
        deltas = "、".join(f"{delta:.0f}%" for delta in evidence["recent_deltas"])
        parts.append(f"最近 {FREQUENT_ADJUSTMENT_WINDOW} 次调整幅度都超过 20%（{deltas}）")
    if REASON_GOAL_CONFLICT in reasons:
        parts.append("目标方向与体重 / 体脂变化趋势相反")
    return (
        "；".join(parts)
        + "。本次调整不会自动改动计划，请确认后再生效；"
        + f"{INTERRUPT_TTL_SECONDS // 60} 分钟内未选择将按推荐方案自动应用。"
    )


def build_interrupt_payload(
    signal: InterruptSignal,
    *,
    now: datetime.datetime,
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    """挂起载荷。``evaluation`` 是本次已算出的评估快照，供 resume / 超时复用，
    避免用户拍板时重新评估（重新评估会和当时展示的选项不一致）。"""
    expires_at = now + datetime.timedelta(seconds=INTERRUPT_TTL_SECONDS)
    recommended = next(
        (option for option in INTERRUPT_OPTIONS if option.recommended),
        INTERRUPT_OPTIONS[0],
    )
    return {
        # 主原因码是首条；reason_codes 保留全部命中，前端可同时展示多个。
        "reason_code": signal.reason_codes[0],
        "reason_codes": list(signal.reason_codes),
        "risk_level": _risk_level(signal.reason_codes),
        "summary": signal.summary,
        "evidence": dict(signal.evidence),
        "proposed_adjustment": recommended.to_dict(),
        "options": [option.to_dict() for option in INTERRUPT_OPTIONS],
        "expires_at": expires_at.isoformat(),
        "evaluation": dict(evaluation),
    }


def _risk_level(reasons: Sequence[str]) -> str:
    """风险档位：伤病风险是高危，其余（频繁大幅调整 / 目标冲突）是中危。"""
    return "high" if REASON_INJURY_RISK in reasons else "medium"


def recommended_option(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """推荐项：载荷里标了 ``recommended`` 的第一项；载荷损坏时退回固定推荐。"""
    options = payload.get("options") if isinstance(payload, Mapping) else None
    if isinstance(options, list):
        for entry in options:
            if isinstance(entry, Mapping) and entry.get("recommended"):
                return dict(entry)
        if options and isinstance(options[0], Mapping):
            return dict(options[0])
    return _OPTIONS_BY_ID[OPTION_REDUCE_INTENSITY].to_dict()


def find_option(
    payload: Mapping[str, Any] | None, option_id: str
) -> dict[str, Any] | None:
    options = payload.get("options") if isinstance(payload, Mapping) else None
    if isinstance(options, list):
        for entry in options:
            if isinstance(entry, Mapping) and entry.get("id") == option_id:
                return dict(entry)
    return None


def option_effect(option: Mapping[str, Any]) -> tuple[str, float]:
    """把选项投影成落地方向与幅度；损坏的选项按「保持」处理，绝不放大风险。"""
    direction = option.get("direction")
    if direction not in (DIRECTION_INCREASE, DIRECTION_DECREASE, DIRECTION_KEEP):
        direction = DIRECTION_KEEP
    raw = option.get("magnitude_percent")
    magnitude = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0.0
    return str(direction), magnitude


def build_landed_reason(
    option: Mapping[str, Any],
    merged: Mapping[str, Any],
    *,
    chosen_by: str,
) -> str:
    """落盘理由：必须提到用户选了什么，以及是谁做的决定（用户 / 超时默认）。"""
    direction, magnitude = option_effect(option)
    label = str(option.get("label") or option.get("id") or "所选方案")
    if direction == DIRECTION_DECREASE:
        action = f"减量 {magnitude:.0f}%"
    elif direction == DIRECTION_INCREASE:
        action = f"加量 {magnitude:.0f}%"
    else:
        action = "保持训练量"
    actor = "用户选择" if chosen_by == CHOSEN_BY_USER else "超时未选择，已按推荐方案"
    overall = merged.get("overall_score")
    score_text = (
        f"整体健康分 {float(overall):.1f}，"
        if isinstance(overall, (int, float)) and not isinstance(overall, bool)
        else ""
    )
    return f"{actor}「{label}」：{score_text}本次{action}"[:255]
