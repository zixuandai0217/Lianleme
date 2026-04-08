"""
VisionGraph：体型分析 LangGraph DAG
节点流程：vision_node（多模态识别）→ parse_node（PydanticOutputParser）→ plan_node（生成训练计划）
"""
import base64
from typing import Any, Optional, TypedDict

from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.schemas.vision import BodyAnalysisResult
from app.services.ai.llm_factory import LLMClientFactory


class VisionState(TypedDict):
    """LangGraph 状态：贯穿整条 DAG 的共享数据"""
    image_base64: str
    profile: Optional[dict]
    user_id: int
    raw_analysis: str        # vision_node 输出的原始文本
    body_analysis: Optional[BodyAnalysisResult]  # parse_node 结构化后的结果
    error: Optional[str]


class VisionGraph:
    """体型分析三节点 DAG"""

    def __init__(self, user_id: int, db=None):
        self.user_id = user_id
        self.db = db
        self.factory = LLMClientFactory(db)
        self.parser = PydanticOutputParser(pydantic_object=BodyAnalysisResult)
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        """构建 LangGraph DAG"""
        graph = StateGraph(VisionState)
        graph.add_node("vision_node", self._vision_node)
        graph.add_node("parse_node", self._parse_node)
        graph.set_entry_point("vision_node")
        graph.add_edge("vision_node", "parse_node")
        graph.add_edge("parse_node", END)
        return graph.compile()

    async def run(
        self, image_base64: str, profile: Optional[dict] = None
    ) -> BodyAnalysisResult:
        """执行体型分析 DAG，返回结构化体型分析结果"""
        initial_state: VisionState = {
            "image_base64": image_base64,
            "profile": profile,
            "user_id": self.user_id,
            "raw_analysis": "",
            "body_analysis": None,
            "error": None,
        }
        result = await self._graph.ainvoke(initial_state)
        if result.get("error"):
            raise RuntimeError(result["error"])
        return result["body_analysis"]

    async def _vision_node(self, state: VisionState) -> dict:
        """多模态节点：调用视觉模型分析体型图片"""
        try:
            llm = await self.factory.get_client(user_id=state["user_id"], model_type="vision")
            profile_text = ""
            if state.get("profile"):
                p = state["profile"]
                profile_text = (
                    f"用户信息：身高 {p.get('height', '未知')}cm，"
                    f"体重 {p.get('weight', '未知')}kg，"
                    f"目标：{p.get('goal', '未知')}，"
                    f"训练经验：{p.get('experience', '未知')}"
                )

            format_instructions = self.parser.get_format_instructions()
            message = HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{state['image_base64']}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"你是专业健身教练，请分析这张全身照的体型特征。{profile_text}\n\n"
                            "请评估：体型分类（ectomorph/mesomorph/endomorph）、估算体脂区间、"
                            "弱势肌群、优势部位、各部位评分（0-10用于雷达图）以及综合建议。\n\n"
                            f"{format_instructions}"
                        ),
                    },
                ]
            )
            response = await llm.ainvoke([message])
            return {"raw_analysis": response.content}
        except Exception as e:
            return {"error": f"体型分析失败：{str(e)}"}

    async def _parse_node(self, state: VisionState) -> dict:
        """解析节点：将原始文本用 PydanticOutputParser 结构化"""
        if state.get("error"):
            return {}
        try:
            result = self.parser.parse(state["raw_analysis"])
            return {"body_analysis": result}
        except Exception as e:
            # 解析失败时尝试宽松降级处理
            fallback = BodyAnalysisResult(
                body_type="mesomorph",
                body_fat_range="未知",
                weak_muscles=[],
                strengths=[],
                muscle_scores={},
                summary=state["raw_analysis"][:500],
            )
            return {"body_analysis": fallback}
