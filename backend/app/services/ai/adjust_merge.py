"""Merge Node：把五份分析器输出压成单一决策依据（工单 24）。

聚合规则（spec §4，ADR-0009）：

- **等权平均**：规则型与模型型同权，不因实现方式加权；``default`` 维度（完全缺省）
  的权重不计入平均，并列入 ``excluded_dimensions`` 供前端标注。
- **红标志旁路**：红标志只决定「是否中断」，不参与平均分，避免高风险被平均分稀释。
  工单 24 只产出当前数据足以判定的红标志：伤病风险（工单 25 接入后生效）、完成率
  过低、疲劳过高；「频繁大幅调整」与「减脂期体重上升」需要调整历史与体重趋势，
  按工单 27 接入。
- **top_reasons**：先取红标志关联维度的理由，再取分数极端的一两条，最多 3 条。
- **方向**：只看 ``overall_score``（≥7.5 加量、5.0-7.5 保持、<5.0 减量）；与完成率
  极值指向的方向冲突时取更保守的一方，避免切换实现的那一周方向反复横跳。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.services.ai.adjust_analyzers import (
    COMPLETENESS_DEFAULT,
    COMPLETENESS_FULL,
    COMPLETENESS_PARTIAL,
    DIMENSION_COMPLETION,
    DIMENSION_FATIGUE,
    DIMENSION_INJURY_RISK,
    AnalyzerResult,
    order_dimensions,
)

DIRECTION_INCREASE = "increase"
DIRECTION_DECREASE = "decrease"
DIRECTION_KEEP = "keep"

# 越靠后越保守：冲突时取序号更大的一方。
_CONSERVATISM = {DIRECTION_INCREASE: 0, DIRECTION_KEEP: 1, DIRECTION_DECREASE: 2}

# 幅度沿用现状量级：加量 10-15%、减量 15-20%，取区间中点作为声明值。
DIRECTION_DELTA_PERCENT = {
    DIRECTION_INCREASE: 12.0,
    DIRECTION_DECREASE: 18.0,
    DIRECTION_KEEP: 0.0,
}

OVERALL_INCREASE_THRESHOLD = 7.5
OVERALL_DECREASE_THRESHOLD = 5.0
COMPLETION_INCREASE_EXTREME = 0.8
COMPLETION_DECREASE_EXTREME = 0.5

RED_FLAG_INJURY_RISK = "injury_risk_high"
RED_FLAG_COMPLETION_LOW = "completion_low"
RED_FLAG_FATIGUE_HIGH = "fatigue_high"
INJURY_RISK_RED_FLAG_SCORE = 3.0
COMPLETION_LOW_RED_FLAG_RATE = 0.5
FATIGUE_HIGH_RED_FLAG_SCORE = 5.0
MAX_TOP_REASONS = 3

# 红标志 → 关联维度：top_reasons 优先取这一维的理由。
_RED_FLAG_DIMENSION = {
    RED_FLAG_INJURY_RISK: DIMENSION_INJURY_RISK,
    RED_FLAG_COMPLETION_LOW: DIMENSION_COMPLETION,
    RED_FLAG_FATIGUE_HIGH: DIMENSION_FATIGUE,
}


@dataclass(frozen=True)
class MergedResult:
    """本周状态小结（对外形状见 spec §4）。"""

    overall_score: float
    dimension_scores: dict[str, float]
    red_flags: list[dict[str, str]] = field(default_factory=list)
    top_reasons: list[str] = field(default_factory=list)
    degraded_dimensions: list[str] = field(default_factory=list)
    excluded_dimensions: list[str] = field(default_factory=list)
    completeness: str = COMPLETENESS_FULL

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": float(self.overall_score),
            "dimension_scores": dict(self.dimension_scores),
            "red_flags": [dict(flag) for flag in self.red_flags],
            "top_reasons": list(self.top_reasons),
            "degraded_dimensions": list(self.degraded_dimensions),
            "excluded_dimensions": list(self.excluded_dimensions),
            "completeness": self.completeness,
        }


def _completeness(ordered: Sequence[AnalyzerResult]) -> str:
    if not ordered:
        return COMPLETENESS_DEFAULT
    if all(result.data_completeness == COMPLETENESS_DEFAULT for result in ordered):
        return COMPLETENESS_DEFAULT
    if all(result.data_completeness == COMPLETENESS_FULL for result in ordered):
        return COMPLETENESS_FULL
    return COMPLETENESS_PARTIAL


def _red_flags(
    ordered: Sequence[AnalyzerResult], completion_rate: float | None
) -> list[dict[str, str]]:
    """当前数据足以判定的风险信号；历史幅度与目标偏离按工单 27 接入。"""
    flags: list[dict[str, str]] = []

    injury = next(
        (result for result in ordered if result.name == DIMENSION_INJURY_RISK), None
    )
    if (
        injury is not None
        and injury.data_completeness != COMPLETENESS_DEFAULT
        and injury.score <= INJURY_RISK_RED_FLAG_SCORE
    ):
        flags.append(
            {
                "code": RED_FLAG_INJURY_RISK,
                "severity": "high",
                "evidence": (
                    f"伤病风险健康评分 {injury.score:.1f} ≤ "
                    f"{INJURY_RISK_RED_FLAG_SCORE:.0f}"
                ),
            }
        )

    if completion_rate is not None and completion_rate < COMPLETION_LOW_RED_FLAG_RATE:
        flags.append(
            {
                "code": RED_FLAG_COMPLETION_LOW,
                "severity": "high",
                "evidence": (
                    f"完成率 {completion_rate:.0%} 低于 "
                    f"{COMPLETION_LOW_RED_FLAG_RATE:.0%}"
                ),
            }
        )

    fatigue = next(
        (result for result in ordered if result.name == DIMENSION_FATIGUE), None
    )
    if (
        fatigue is not None
        and fatigue.data_completeness != COMPLETENESS_DEFAULT
        and fatigue.score <= FATIGUE_HIGH_RED_FLAG_SCORE
    ):
        flags.append(
            {
                "code": RED_FLAG_FATIGUE_HIGH,
                "severity": "medium",
                "evidence": (
                    f"疲劳度健康评分 {fatigue.score:.1f} ≤ "
                    f"{FATIGUE_HIGH_RED_FLAG_SCORE:.0f}"
                ),
            }
        )
    return flags


def _top_reasons(
    ordered: Sequence[AnalyzerResult],
    participating: Sequence[AnalyzerResult],
    red_flags: Sequence[Mapping[str, str]],
) -> list[str]:
    """最多 3 条：红标志关联维度优先，其次最低/最高分，最后按顺序补齐。"""
    selected: list[str] = []

    def push(reason: str | None) -> None:
        if reason and reason not in selected and len(selected) < MAX_TOP_REASONS:
            selected.append(reason)

    for flag in red_flags:
        dimension_name = _RED_FLAG_DIMENSION.get(flag.get("code", ""))
        dimension = next(
            (result for result in ordered if result.name == dimension_name), None
        )
        if dimension is not None:
            push(dimension.reason)

    if participating:
        order = {result.name: index for index, result in enumerate(ordered)}
        lowest = min(participating, key=lambda result: (result.score, order[result.name]))
        highest = max(participating, key=lambda result: (result.score, -order[result.name]))
        push(lowest.reason)
        push(highest.reason)

    for result in participating:
        push(result.reason)
    return selected


def merge_results(
    dimensions: Iterable[AnalyzerResult],
    *,
    completion_rate: float | None = None,
) -> MergedResult:
    """把五份分析器输出压成单一决策依据。"""
    ordered = order_dimensions(dimensions)
    participating = [
        result
        for result in ordered
        if result.data_completeness != COMPLETENESS_DEFAULT
    ]
    overall = (
        round(sum(result.score for result in participating) / len(participating), 2)
        if participating
        else 0.0
    )
    red_flags = _red_flags(ordered, completion_rate)
    return MergedResult(
        overall_score=overall,
        dimension_scores={result.name: float(result.score) for result in ordered},
        red_flags=red_flags,
        top_reasons=_top_reasons(ordered, participating, red_flags),
        degraded_dimensions=[
            result.name for result in ordered if result.degraded
        ],
        excluded_dimensions=[
            result.name
            for result in ordered
            if result.data_completeness == COMPLETENESS_DEFAULT
        ],
        completeness=_completeness(ordered),
    )


def decide_direction(
    overall_score: float,
    completion_rate: float | None,
    *,
    participating: bool = True,
) -> str:
    """路由只看合并分；与完成率极值冲突时取更保守的一方（spec §5）。"""
    if not participating:
        # 全维缺省：评估不可用，走保守动作而不是编造一个分数。
        return DIRECTION_KEEP

    if overall_score >= OVERALL_INCREASE_THRESHOLD:
        direction = DIRECTION_INCREASE
    elif overall_score < OVERALL_DECREASE_THRESHOLD:
        direction = DIRECTION_DECREASE
    else:
        direction = DIRECTION_KEEP

    if completion_rate is None:
        return direction
    if completion_rate >= COMPLETION_INCREASE_EXTREME:
        extreme = DIRECTION_INCREASE
    elif completion_rate < COMPLETION_DECREASE_EXTREME:
        extreme = DIRECTION_DECREASE
    else:
        return direction

    if _CONSERVATISM[extreme] > _CONSERVATISM[direction]:
        return extreme
    return direction


def delta_percent_for(direction: str) -> float:
    """方向对应的声明幅度（百分比，0 表示保持）。"""
    return DIRECTION_DELTA_PERCENT.get(direction, 0.0)


def build_reason(
    merged: MergedResult,
    direction: str,
    completion_rate: float | None,
    *,
    participating: bool = True,
) -> str:
    """一句人话理由：含整体健康分与触发数值，长度控制在落盘列宽内。"""
    if not participating:
        return "本次缺少可用评估数据，保守保持当前训练量（数据为缺省）"

    delta = delta_percent_for(direction)
    if direction == DIRECTION_INCREASE:
        action = f"五维体检整体良好，本次加量 {delta:.0f}%"
    elif direction == DIRECTION_DECREASE:
        action = f"五维体检整体偏弱，本次减量 {delta:.0f}%"
    else:
        action = "五维体检整体平稳，本次保持训练量"
    rate_text = "完成率未知" if completion_rate is None else f"完成率 {completion_rate:.0%}"
    return f"整体健康分 {merged.overall_score:.1f}（{rate_text}），{action}"
