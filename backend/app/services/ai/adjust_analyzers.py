"""五路分析器的统一契约与三路确定性规则（工单 24）。

ADR-0001 定义统一输出 ``{score, reason, suggestion}``，本 spec 在此基础上补齐
``source``（规则 / 模型）、``degraded``（是否降级运行）与 ``data_completeness``
（真实数据 / 部分真实 / 完全缺省）。``score`` 一律是**健康评分**：10 最好、0 最差；
模型侧若给出「风险值」，必须在分析器内部翻转成健康评分再出栈。

本票只实现三路确定性规则（completion / fatigue / sleep），两路模型维度
（injury_risk / body_composition）以「未评估」占位，保证五维形状恒定。
占位与规则都不调用模型：工单 25 才接入真实 LLM 分析器。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DIMENSION_COMPLETION = "completion"
DIMENSION_FATIGUE = "fatigue"
DIMENSION_INJURY_RISK = "injury_risk"
DIMENSION_SLEEP = "sleep"
DIMENSION_BODY_COMPOSITION = "body_composition"

# 五路输出顺序固定（按 spec 的实现表顺序），不依赖完成先后，避免展示顺序抖动。
DIMENSION_ORDER: tuple[str, ...] = (
    DIMENSION_COMPLETION,
    DIMENSION_FATIGUE,
    DIMENSION_INJURY_RISK,
    DIMENSION_SLEEP,
    DIMENSION_BODY_COMPOSITION,
)

RULE_DIMENSIONS: tuple[str, ...] = (
    DIMENSION_COMPLETION,
    DIMENSION_FATIGUE,
    DIMENSION_SLEEP,
)
LLM_DIMENSIONS: tuple[str, ...] = (DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION)

SOURCE_RULE = "rule"
SOURCE_LLM = "llm"

COMPLETENESS_FULL = "full"
COMPLETENESS_PARTIAL = "partial"
COMPLETENESS_DEFAULT = "default"

# 缺省值来自 ADR-0001「用户不填写时使用默认值（fatigue=3, sleep=3）」与 spec §8。
DEFAULT_FATIGUE_SCORE = 3
DEFAULT_SLEEP_HOURS = 7.0
DEFAULT_SLEEP_QUALITY = 3
DEFAULT_MISSING_MARK = "数据为缺省"

# 缺省 / 失败时的中性分：不参与平均，但保证条目形状完整、展示不出现空值。
NEUTRAL_SCORE = 5.0


class InvalidAnalyzerInput(ValueError):
    """该维度的输入不合法：由该维度自己降级，不冒泡到 Merge 之前。"""


@dataclass(frozen=True)
class AnalyzerResult:
    """单维分析结果（对外统一形状）。"""

    name: str
    score: float
    reason: str
    suggestion: str
    source: str = SOURCE_RULE
    degraded: bool = False
    data_completeness: str = COMPLETENESS_FULL

    def to_dict(self) -> dict[str, Any]:
        """固定字段顺序的对外形状；下游（合并 / 落盘 / 读取）只认这一份。"""
        return {
            "name": self.name,
            "score": float(self.score),
            "reason": self.reason,
            "suggestion": self.suggestion,
            "source": self.source,
            "degraded": bool(self.degraded),
            "data_completeness": self.data_completeness,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AnalyzerResult:
        """把落盘/Graph 状态里的条目还原成结果对象。"""
        return cls(
            name=str(payload["name"]),
            score=float(payload["score"]),
            reason=str(payload.get("reason") or ""),
            suggestion=str(payload.get("suggestion") or ""),
            source=str(payload.get("source") or SOURCE_RULE),
            degraded=bool(payload.get("degraded", False)),
            data_completeness=str(payload.get("data_completeness") or COMPLETENESS_FULL),
        )


def order_dimensions(dimensions: Iterable[AnalyzerResult]) -> list[AnalyzerResult]:
    """按固定维度顺序排列；未知维度排在最后，保证顺序稳定。"""
    order = {name: index for index, name in enumerate(DIMENSION_ORDER)}
    return sorted(
        dimensions,
        key=lambda result: (order.get(result.name, len(order)), result.name),
    )


def _as_sequence(value: Any) -> list[Any]:
    """单值也接受：``3`` 与 ``[3]`` 同义，避免调用方为凑形状而包装。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _as_rate(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidAnalyzerInput("完成率必须是 0-1 的数值")
    rate = float(value)
    if not 0.0 <= rate <= 1.0:
        raise InvalidAnalyzerInput("完成率必须落在 0-1 区间")
    return rate


def _as_rating(value: Any, *, label: str) -> int:
    """1-5 的主观评分（疲劳度 / 睡眠质量）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidAnalyzerInput(f"{label}必须是 1-5 的数值")
    number = float(value)
    if not number.is_integer() or not 1 <= number <= 5:
        raise InvalidAnalyzerInput(f"{label}必须落在 1-5 区间")
    return int(number)


def _as_hours(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidAnalyzerInput("睡眠时长必须是数值（小时）")
    hours = float(value)
    if not 0.0 <= hours <= 24.0:
        raise InvalidAnalyzerInput("睡眠时长必须落在 0-24 小时")
    return hours


def completion_score(average_rate: float) -> float:
    """ADR-0003：完成率 ≥0.85→9、0.7-0.85→7、<0.7→5。"""
    if average_rate >= 0.85:
        return 9.0
    if average_rate >= 0.7:
        return 7.0
    return 5.0


def fatigue_score(average_rating: float) -> float:
    """ADR-0003：疲劳 1-2→9-10、3→7、4-5→3-5（线性落到整数档）。"""
    if average_rating <= 1.5:
        return 10.0
    if average_rating <= 2.5:
        return 9.0
    if average_rating <= 3.5:
        return 7.0
    if average_rating <= 4.5:
        return 5.0
    return 3.0


def sleep_score(hours: float, quality: int) -> float:
    """ADR-0003：≥7h 且质量 ≥4→9、6-7h→7、<6h→5。

    睡够但主观质量差（<4）按 6-7h 档的 7 分处理：时长达标、恢复感不足，
    仍优于「不足 6 小时」。
    """
    if hours >= 7.0 and quality >= 4:
        return 9.0
    if hours >= 6.0:
        return 7.0
    return 5.0


def analyze_completion(payload: Mapping[str, Any]) -> AnalyzerResult:
    """完成率规则：近 7 天完成率序列的均值。"""
    rates = [_as_rate(value) for value in _as_sequence(payload.get("completion_rates"))]
    if not rates:
        return AnalyzerResult(
            name=DIMENSION_COMPLETION,
            score=NEUTRAL_SCORE,
            reason=f"近 7 天没有可用的完成率数据，{DEFAULT_MISSING_MARK}，本次不参与合并评分",
            suggestion="先完成一次训练打卡，再评估完成率",
            source=SOURCE_RULE,
            degraded=True,
            data_completeness=COMPLETENESS_DEFAULT,
        )

    average = sum(rates) / len(rates)
    score = completion_score(average)
    if score >= 9:
        state, suggestion = "表现优秀", "可以适当增加训练量（10-15%）"
    elif score >= 7:
        state, suggestion = "表现良好", "保持当前训练量"
    else:
        state, suggestion = "略显吃力", "建议降低训练量 15-20%"
    return AnalyzerResult(
        name=DIMENSION_COMPLETION,
        score=score,
        reason=f"近 7 天平均完成率 {average:.0%}，{state}",
        suggestion=suggestion,
        source=SOURCE_RULE,
    )


def analyze_fatigue(payload: Mapping[str, Any]) -> AnalyzerResult:
    """疲劳度规则：用户自评 1-5；无数据按缺省 3 分并明确标注。"""
    ratings = [
        _as_rating(value, label="疲劳度")
        for value in _as_sequence(payload.get("fatigue_scores"))
    ]
    if not ratings:
        return AnalyzerResult(
            name=DIMENSION_FATIGUE,
            score=fatigue_score(DEFAULT_FATIGUE_SCORE),
            reason=(
                f"未采集到疲劳度自评，按缺省值 {DEFAULT_FATIGUE_SCORE} 分评估"
                f"（{DEFAULT_MISSING_MARK}）"
            ),
            suggestion="打卡表单补齐疲劳度自评后，该维度会更有参考价值",
            source=SOURCE_RULE,
            degraded=True,
            data_completeness=COMPLETENESS_DEFAULT,
        )

    average = sum(ratings) / len(ratings)
    score = fatigue_score(average)
    if score >= 9:
        suggestion = "状态充沛，可以按计划推进"
    elif score >= 7:
        suggestion = "保持当前强度，注意恢复"
    else:
        suggestion = "建议降低强度或插入休息日"
    return AnalyzerResult(
        name=DIMENSION_FATIGUE,
        score=score,
        reason=f"本周疲劳度自评 {average:.1f}（1-5），疲劳越高评分越低",
        suggestion=suggestion,
        source=SOURCE_RULE,
    )


def analyze_sleep(payload: Mapping[str, Any]) -> AnalyzerResult:
    """睡眠规则：时长 + 主观质量；两者都缺按缺省 7h / 3 分并标注。"""
    raw_hours = payload.get("sleep_hours")
    raw_quality = payload.get("sleep_quality")
    if raw_hours is None and raw_quality is None:
        return AnalyzerResult(
            name=DIMENSION_SLEEP,
            score=sleep_score(DEFAULT_SLEEP_HOURS, DEFAULT_SLEEP_QUALITY),
            reason=(
                f"未采集到睡眠数据，按缺省 {DEFAULT_SLEEP_HOURS:.0f} 小时 / "
                f"质量 {DEFAULT_SLEEP_QUALITY} 分评估（{DEFAULT_MISSING_MARK}）"
            ),
            suggestion="打卡表单补齐睡眠时长与质量后，该维度会更有参考价值",
            source=SOURCE_RULE,
            degraded=True,
            data_completeness=COMPLETENESS_DEFAULT,
        )

    hours = DEFAULT_SLEEP_HOURS if raw_hours is None else _as_hours(raw_hours)
    quality = (
        DEFAULT_SLEEP_QUALITY
        if raw_quality is None
        else _as_rating(raw_quality, label="睡眠质量")
    )
    completeness = (
        COMPLETENESS_FULL if raw_hours is not None and raw_quality is not None
        else COMPLETENESS_PARTIAL
    )
    score = sleep_score(hours, quality)
    if score >= 9:
        suggestion = "恢复良好，可以正常训练"
    elif score >= 7:
        suggestion = "睡眠一般，避免连续安排高强度训练"
    else:
        suggestion = "睡眠不足，建议降低强度并优先补觉"
    reason = f"睡眠 {hours:.1f} 小时、主观质量 {quality} 分（1-5）"
    if completeness == COMPLETENESS_PARTIAL:
        missing = "睡眠质量" if raw_quality is None else "睡眠时长"
        reason = f"{reason}，{missing}未采集按缺省值补齐（{DEFAULT_MISSING_MARK}）"
    return AnalyzerResult(
        name=DIMENSION_SLEEP,
        score=score,
        reason=reason,
        suggestion=suggestion,
        source=SOURCE_RULE,
        degraded=False,
        data_completeness=completeness,
    )


def not_evaluated(name: str) -> AnalyzerResult:
    """模型维度的「未评估」占位：形状完整、明确降级、不发起任何调用。"""
    return AnalyzerResult(
        name=name,
        score=NEUTRAL_SCORE,
        reason=f"本票未接入模型分析，{name} 维度本次未评估（{DEFAULT_MISSING_MARK}）",
        suggestion="下一版接入模型分析后补齐该维度的判断",
        source=SOURCE_LLM,
        degraded=True,
        data_completeness=COMPLETENESS_DEFAULT,
    )


# 规则维度注册表。测试与工单 25 都从这里替换/扩展实现，而不是改 Graph 拓扑。
ANALYZERS: dict[str, Callable[[Mapping[str, Any]], AnalyzerResult]] = {
    DIMENSION_COMPLETION: analyze_completion,
    DIMENSION_FATIGUE: analyze_fatigue,
    DIMENSION_SLEEP: analyze_sleep,
}


def _degraded_result(name: str) -> AnalyzerResult:
    """单路失败时的降级输出：中性分、显式降级、从合并中剔除。"""
    source = SOURCE_LLM if name in LLM_DIMENSIONS else SOURCE_RULE
    return AnalyzerResult(
        name=name,
        score=NEUTRAL_SCORE,
        reason=f"{name} 维度输入异常，本次已降级为中性分（{DEFAULT_MISSING_MARK}）",
        suggestion="本次跳过该维度，其余维度照常评估",
        source=source,
        degraded=True,
        data_completeness=COMPLETENESS_DEFAULT,
    )


def run_analyzer(name: str, payload: Mapping[str, Any]) -> AnalyzerResult:
    """执行单维分析：异常必须由该路自己吞掉，绝不冒泡到 Merge 之前。"""
    if name in LLM_DIMENSIONS:
        return not_evaluated(name)
    analyzer = ANALYZERS.get(name)
    if analyzer is None:
        raise ValueError(f"未知的分析维度：{name}")
    try:
        return analyzer(payload)
    except Exception:  # noqa: BLE001 - 单路失败隔离是并行编排的硬要求
        return _degraded_result(name)


def evaluate_dimensions(payload: Mapping[str, Any]) -> list[AnalyzerResult]:
    """顺序执行五维（固定顺序）；Graph 里同一批分析器并行执行，结果一致。"""
    return [run_analyzer(name, payload) for name in DIMENSION_ORDER]


def build_evaluation_input(
    *,
    completion_rate: float | None,
    difficulty_rating: float | None = None,
    fatigue_scores: Sequence[int] | None = None,
    sleep_hours: float | None = None,
    sleep_quality: int | None = None,
) -> dict[str, Any]:
    """analyze_input 的取材结果：只做裁剪与缺省填充，不做判断。

    本票没有疲劳 / 睡眠的打卡字段，因此这两项通常为空、由分析器走缺省；
    ``difficulty_rating`` 只随输入下行留档，不当作疲劳代理——打卡路由会把缺省的
    难度自评归一成 3，用它做代理会让「无数据」与「自评 3」不可区分，与 AC3 的
    缺省标注冲突（代理留给打卡表单扩展时与真实疲劳字段一起接入）。
    """
    return {
        "completion_rates": _as_sequence(completion_rate),
        "fatigue_scores": _as_sequence(fatigue_scores),
        "sleep_hours": sleep_hours,
        "sleep_quality": sleep_quality,
        "difficulty_rating": difficulty_rating,
    }
