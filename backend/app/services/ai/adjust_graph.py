"""AdjustGraph：五路并行分析 → Merge → 决策 → 落地（工单 24）。

拓扑来自 ADR-0001：``analyze_input → [completion | fatigue | injury_risk | sleep |
body_composition] → merge_results → decision → apply_*``。

三路规则与两路模型在两个层面运行：规则维度即时出分，模型维度（伤病风险 /
体重体脂趋势）在模型可用时返回结构化评分，不可用或失败时由该路自己降级为
规则近似。模型客户端与聚合摘要由调用方通过 ``LlmAnalyzerContext`` 注入，
Graph 本身不拼 Prompt、也不决定隐私边界。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.services.ai.adjust_analyzers import (
    COMPLETENESS_DEFAULT,
    DIMENSION_ORDER,
    LLM_DIMENSIONS,
    RULE_DIMENSIONS,
    AnalyzerResult,
    build_evaluation_input,
    order_dimensions,
    run_analyzer,
    run_llm_analyzer,
)
from app.services.ai.adjust_merge import (
    DIRECTION_DECREASE,
    DIRECTION_INCREASE,
    DIRECTION_KEEP,
    MergedResult,
    build_reason,
    decide_direction,
    delta_percent_for,
    merge_results,
)
from app.services.ai.llm_adjust_analyzers import (
    LlmAnalyzerContext,
    resolve_llm_context,
)
from app.services.ai.llm_factory import LLMClientFactory

_DIRECTIONS = (DIRECTION_INCREASE, DIRECTION_DECREASE, DIRECTION_KEEP)


def _merge_degradation_reasons(
    left: dict[str, str] | None, right: dict[str, str] | None
) -> dict[str, str]:
    """并行节点各写各的降级分类：按维度名合并，避免后到者覆盖先到者。"""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class AdjustState(TypedDict, total=False):
    """计划调整状态（LangGraph 的共享状态）。"""

    user_id: int
    completion_rate: float
    difficulty_rating: Optional[float]
    current_plan: dict
    fatigue_scores: list[int]
    sleep_hours: Optional[float]
    sleep_quality: Optional[int]
    evaluation_input: dict
    llm_context: Any
    # 五路并行写入：reducer 负责拼接，顺序由 DIMENSION_ORDER 在出口归一。
    dimensions: Annotated[list[dict], operator.add]
    degradation_reasons: Annotated[dict[str, str], _merge_degradation_reasons]
    merged: dict
    adjustment_type: str
    delta_percent: float
    reason: str
    adjusted_plan: Optional[dict]


def apply_direction(plan: dict, direction: str, delta_percent: float) -> dict:
    """确定性地落地方向：按声明幅度缩放计划的整体难度系数。

    本票不调用模型，因此不做「让模型改写动作列表」的落地；整数动作组数无法表达
    10-15% 的幅度，用已有的 ``difficulty_factor`` 精确表达声明幅度，动作清单原样保留。
    逐动作的组数/次数重排属于工单 27/28 的落地语义。
    """
    adjusted = dict(plan or {})
    factor = float(adjusted.get("difficulty_factor") or 1.0)
    if direction == DIRECTION_INCREASE:
        adjusted["difficulty_factor"] = round(factor * (1 + delta_percent / 100), 4)
    elif direction == DIRECTION_DECREASE:
        adjusted["difficulty_factor"] = round(factor * (1 - delta_percent / 100), 4)
    return adjusted


def _analyzer_node_name(dimension: str) -> str:
    return f"analyze_{dimension}"


def _apply_node_name(direction: str) -> str:
    return f"apply_{direction}"


class AdjustGraph:
    """训练计划动态调整 Graph（五路并行分析 + 合并决策）。"""

    def __init__(
        self,
        user_id: int,
        db=None,
        *,
        llm_context: LlmAnalyzerContext | None = None,
    ):
        self.user_id = user_id
        self.db = db
        # 调用方（PlanService）注入客户端与聚合摘要；直接使用 Graph 时按需解析。
        self.llm_context = llm_context
        self.factory = LLMClientFactory(db)
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(AdjustState)
        graph.add_node("analyze_input", self._analyze_input_node)
        for dimension in DIMENSION_ORDER:
            graph.add_node(_analyzer_node_name(dimension), self._analyzer_node(dimension))
        graph.add_node("merge_results", self._merge_node)
        graph.add_node("decision", self._decision_node)
        for direction in _DIRECTIONS:
            graph.add_node(_apply_node_name(direction), self._apply_node(direction))

        graph.set_entry_point("analyze_input")
        # 五路在同一层 fan-out：聚合前没有中间同步点，总耗时等于最慢一路。
        for dimension in DIMENSION_ORDER:
            graph.add_edge("analyze_input", _analyzer_node_name(dimension))
            graph.add_edge(_analyzer_node_name(dimension), "merge_results")
        graph.add_edge("merge_results", "decision")
        graph.add_conditional_edges(
            "decision",
            self._route_direction,
            {direction: _apply_node_name(direction) for direction in _DIRECTIONS},
        )
        for direction in _DIRECTIONS:
            graph.add_edge(_apply_node_name(direction), END)
        return graph.compile()

    @staticmethod
    def _route_direction(state: AdjustState) -> str:
        """条件边：方向在 decision 节点已经算好，这里只做路由。"""
        direction = state.get("adjustment_type") or DIRECTION_KEEP
        return direction if direction in _DIRECTIONS else DIRECTION_KEEP

    async def run(
        self,
        completion_rate: float,
        difficulty_rating: Optional[float],
        current_plan: dict,
        *,
        fatigue_scores: Optional[list[int]] = None,
        sleep_hours: Optional[float] = None,
        sleep_quality: Optional[int] = None,
    ) -> dict:
        """执行一次完整评估，返回完整状态（五维明细 + 合并分 + 方向 + 调整后计划）。

        早期实现只返回 ``adjusted_plan``，导致方向与理由在出口被丢弃；出口保持完整
        状态，调用方按需取用（工单 08 的落盘与工单 26 的详情都读这里）。
        """
        initial: AdjustState = {
            "user_id": self.user_id,
            "completion_rate": completion_rate,
            "difficulty_rating": difficulty_rating,
            "current_plan": current_plan or {},
            "fatigue_scores": list(fatigue_scores or []),
            "sleep_hours": sleep_hours,
            "sleep_quality": sleep_quality,
            "llm_context": self.llm_context,
            "dimensions": [],
            "degradation_reasons": {},
            "adjustment_type": "",
            "reason": "",
            "adjusted_plan": None,
        }
        result = await self._graph.ainvoke(initial)
        result["adjusted_plan"] = result.get("adjusted_plan") or current_plan
        result["dimensions"] = [
            entry.to_dict()
            for entry in order_dimensions(
                AnalyzerResult.from_dict(item) for item in result.get("dimensions") or []
            )
        ]
        return result

    async def _analyze_input_node(self, state: AdjustState) -> dict:
        """取材与缺省填充：不做判断，只把输入裁剪成各分析器的切片。"""
        payload = build_evaluation_input(
            completion_rate=state.get("completion_rate"),
            difficulty_rating=state.get("difficulty_rating"),
            fatigue_scores=state.get("fatigue_scores"),
            sleep_hours=state.get("sleep_hours"),
            sleep_quality=state.get("sleep_quality"),
        )
        context = state.get("llm_context")
        if context is None:
            context = await resolve_llm_context(self.factory, self.user_id)
        # 规则维度是确定性的，先把分数并入聚合摘要，模型两维据此做深度判断。
        summary = dict(context.summary or {})
        summary["rule_scores"] = {
            name: run_analyzer(name, payload).score for name in RULE_DIMENSIONS
        }
        context = LlmAnalyzerContext(
            client=context.client,
            summary=summary,
            unavailable_reason=context.unavailable_reason,
        )
        return {"evaluation_input": payload, "llm_context": context}

    def _analyzer_node(self, dimension: str):
        """单个分析器节点：单路异常在这里被吞掉并转成降级输出。"""

        async def node(state: AdjustState) -> dict:
            payload = state.get("evaluation_input") or {}
            if dimension in LLM_DIMENSIONS:
                result = await run_llm_analyzer(
                    dimension, payload, state.get("llm_context")
                )
            else:
                result = run_analyzer(dimension, payload)
            updates: dict[str, Any] = {"dimensions": [result.to_dict()]}
            if result.degradation_reason:
                updates["degradation_reasons"] = {
                    dimension: result.degradation_reason
                }
            return updates

        return node

    async def _merge_node(self, state: AdjustState) -> dict:
        merged = merge_results(
            [AnalyzerResult.from_dict(item) for item in state.get("dimensions") or []],
            completion_rate=state.get("completion_rate"),
            degradation_reasons=state.get("degradation_reasons") or {},
        )
        return {"merged": merged.to_dict()}

    async def _decision_node(self, state: AdjustState) -> dict:
        """把合并结果映射为方向与声明幅度；全流程只有这一个决策点。"""
        merged = MergedResult(**state["merged"])
        dimensions = [
            AnalyzerResult.from_dict(item) for item in state.get("dimensions") or []
        ]
        participating = any(
            entry.data_completeness != COMPLETENESS_DEFAULT for entry in dimensions
        )
        direction = decide_direction(
            merged.overall_score,
            state.get("completion_rate"),
            participating=participating,
        )
        return {
            "adjustment_type": direction,
            "delta_percent": delta_percent_for(direction),
            "reason": build_reason(
                merged,
                direction,
                state.get("completion_rate"),
                participating=participating,
            ),
        }

    def _apply_node(self, direction: str):
        """落地节点：确定性地把方向写回计划，不调用模型。"""

        async def node(state: AdjustState) -> dict:
            return {
                "adjusted_plan": apply_direction(
                    state.get("current_plan") or {},
                    direction,
                    float(state.get("delta_percent") or 0.0),
                )
            }

        return node
