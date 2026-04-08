"""
CoachGraph：AI 陪练 LangGraph StateGraph 状态机
节点：greet → guide_exercise ↔ count_reps → rest_reminder → next_exercise → workout_complete
使用 RedisChatMessageHistory 持久化用户对话历史（TTL=24h）
"""
import json
from typing import Any, AsyncIterator, Optional, TypedDict

from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.schemas.chat import CoachResponse
from app.services.ai.llm_factory import LLMClientFactory

# 陪练状态枚举
STATES = ["greet", "guide", "count", "rest", "next", "complete"]


class CoachState(TypedDict):
    """陪练状态机共享状态"""
    user_id: int
    message: str
    context: dict           # 训练上下文（当前动作/组数等）
    reply: str
    coach_state: str        # 当前节点状态
    suggested_actions: list[str]


class CoachGraph:
    """AI 陪练对话状态机"""

    def __init__(self, user_id: int, db=None):
        self.user_id = user_id
        self.db = db
        self.factory = LLMClientFactory(db)

    def _get_history(self) -> RedisChatMessageHistory:
        """获取 Redis 持久化对话历史（以 user_id 隔离，TTL=24h）"""
        return RedisChatMessageHistory(
            session_id=f"coach:{self.user_id}",
            url=settings.REDIS_URL,
            ttl=86400,
        )

    def _build_system_prompt(self, context: dict) -> str:
        """根据训练上下文动态构建系统 Prompt"""
        exercise = context.get("current_exercise", "训练")
        completed = context.get("completed_sets", 0)
        total = context.get("total_sets", 0)
        return (
            f"你是用户的AI健身搭子，亲切、鼓励、专业。"
            f"当前训练动作：{exercise}，已完成 {completed}/{total} 组。"
            f"根据用户消息给出简短有力的教练回复（50字以内），并在末尾给出1-3个快捷操作建议。"
            f"回复格式：JSON {{\"reply\": \"...\", \"coach_state\": \"guide|count|rest|complete\", "
            f"\"suggested_actions\": [...]}}"
        )

    async def chat(self, message: str, context: dict) -> CoachResponse:
        """普通对话：返回完整 JSON 响应"""
        llm = await self.factory.get_client(user_id=self.user_id, model_type="chat")
        history = self._get_history()

        messages = [SystemMessage(content=self._build_system_prompt(context))]
        messages.extend(history.messages[-10:])  # 最近 10 条历史
        messages.append(HumanMessage(content=message))

        response = await llm.ainvoke(messages)
        history.add_user_message(message)
        history.add_ai_message(response.content)

        try:
            data = json.loads(response.content)
            return CoachResponse(
                reply=data.get("reply", response.content),
                coach_state=data.get("coach_state", "guide"),
                suggested_actions=data.get("suggested_actions", []),
            )
        except json.JSONDecodeError:
            return CoachResponse(
                reply=response.content,
                coach_state="guide",
                suggested_actions=["完成一组", "换个动作", "怎么做"],
            )

    async def stream_chat(
        self, message: str, context: dict
    ) -> AsyncIterator[str]:
        """流式对话：逐 token yield 给 SSE 接口"""
        llm = await self.factory.get_client(
            user_id=self.user_id, model_type="chat", streaming=True
        )
        history = self._get_history()

        messages = [SystemMessage(content=self._build_system_prompt(context))]
        messages.extend(history.messages[-10:])
        messages.append(HumanMessage(content=message))

        full_response = ""
        async for chunk in llm.astream(messages):
            token = chunk.content
            full_response += token
            yield token

        history.add_user_message(message)
        history.add_ai_message(full_response)
