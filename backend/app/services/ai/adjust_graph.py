"""
AdjustGraph：训练计划动态调整 LangGraph 条件分支
流程：analyze_node → 条件边（完成率≥80% → increase_node；<50% → decrease_node；其余 → keep_node）
"""
from typing import Any, Optional, TypedDict

from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.services.ai.llm_factory import LLMClientFactory


class AdjustState(TypedDict):
    """计划调整状态"""
    user_id: int
    completion_rate: float      # 本周完成率 0-1
    difficulty_rating: float    # 用户自评难度均值 1-5
    current_plan: dict          # 当前周训练计划 JSON
    adjustment_type: str        # increase / decrease / keep
    adjusted_plan: Optional[dict]
    reason: str


class AdjustGraph:
    """训练计划难度动态调整 Graph"""

    def __init__(self, user_id: int, db=None):
        self.user_id = user_id
        self.db = db
        self.factory = LLMClientFactory(db)
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(AdjustState)
        graph.add_node("analyze_node", self._analyze_node)
        graph.add_node("increase_node", self._increase_node)
        graph.add_node("decrease_node", self._decrease_node)
        graph.add_node("keep_node", self._keep_node)

        graph.set_entry_point("analyze_node")
        graph.add_conditional_edges(
            "analyze_node",
            self._route_adjustment,
            {
                "increase": "increase_node",
                "decrease": "decrease_node",
                "keep": "keep_node",
            },
        )
        graph.add_edge("increase_node", END)
        graph.add_edge("decrease_node", END)
        graph.add_edge("keep_node", END)
        return graph.compile()

    def _route_adjustment(self, state: AdjustState) -> str:
        """条件边：根据完成率决定调整方向"""
        rate = state["completion_rate"]
        if rate >= 0.8:
            return "increase"
        elif rate < 0.5:
            return "decrease"
        return "keep"

    async def run(
        self,
        completion_rate: float,
        difficulty_rating: float,
        current_plan: dict,
    ) -> dict:
        """执行计划调整，返回修订后的计划 JSON"""
        initial: AdjustState = {
            "user_id": self.user_id,
            "completion_rate": completion_rate,
            "difficulty_rating": difficulty_rating,
            "current_plan": current_plan,
            "adjustment_type": "",
            "adjusted_plan": None,
            "reason": "",
        }
        result = await self._graph.ainvoke(initial)
        return result.get("adjusted_plan") or current_plan

    async def _analyze_node(self, state: AdjustState) -> dict:
        """分析节点：确定调整类型（实际路由由条件边完成）"""
        rate = state["completion_rate"]
        if rate >= 0.8:
            return {"adjustment_type": "increase", "reason": f"完成率 {rate:.0%}，表现优秀，适当加量"}
        elif rate < 0.5:
            return {"adjustment_type": "decrease", "reason": f"完成率 {rate:.0%}，难度过高，适当减量"}
        return {"adjustment_type": "keep", "reason": f"完成率 {rate:.0%}，保持当前难度"}

    async def _increase_node(self, state: AdjustState) -> dict:
        """增量节点：提升 10-15% 训练量"""
        llm = await self.factory.get_client(user_id=state["user_id"], model_type="chat")
        prompt = (
            f"用户本周完成率 {state['completion_rate']:.0%}，表现优秀。"
            f"请将以下训练计划的组数/次数适当提升 10-15%，保持 JSON 格式不变：\n"
            f"{state['current_plan']}"
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"adjusted_plan": self._safe_parse(response.content, state["current_plan"])}

    async def _decrease_node(self, state: AdjustState) -> dict:
        """减量节点：降低 15-20% 训练量"""
        llm = await self.factory.get_client(user_id=state["user_id"], model_type="chat")
        prompt = (
            f"用户本周完成率仅 {state['completion_rate']:.0%}，难度偏高。"
            f"请将以下训练计划的组数/次数适当降低 15-20%，保持 JSON 格式不变：\n"
            f"{state['current_plan']}"
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"adjusted_plan": self._safe_parse(response.content, state["current_plan"])}

    async def _keep_node(self, state: AdjustState) -> dict:
        """保持节点：难度不变，直接返回原计划"""
        return {"adjusted_plan": state["current_plan"]}

    def _safe_parse(self, content: str, fallback: dict) -> dict:
        """安全解析 LLM 返回的 JSON，失败则使用原计划"""
        import json, re
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return fallback
