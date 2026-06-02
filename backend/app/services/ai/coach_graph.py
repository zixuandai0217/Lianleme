"""
CoachGraph：AI 陪练对话引擎
对话历史持久化到 DB（chat_messages 表），LLM 上下文取最近 20 条
"""
import json
import logging
import re
from typing import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.chat_message import ChatMessageRecord
from app.schemas.chat import CoachResponse
from app.services.ai.llm_factory import LLMClientFactory

logger = logging.getLogger(__name__)

CONTEXT_WINDOW = 20


class CoachGraph:
    """AI 陪练对话引擎，对话记录持久化到数据库"""

    def __init__(self, user_id: int, db: AsyncSession | None = None):
        self.user_id = user_id
        self.db = db
        self.factory = LLMClientFactory(db)

    async def _load_history(self, db: AsyncSession) -> list:
        """从 DB 加载最近 N 条对话，转为 LangChain Message 格式"""
        result = await db.execute(
            select(ChatMessageRecord)
            .where(ChatMessageRecord.user_id == self.user_id)
            .order_by(desc(ChatMessageRecord.created_at))
            .limit(CONTEXT_WINDOW)
        )
        records = list(reversed(result.scalars().all()))
        messages = []
        for r in records:
            if r.role == "user":
                messages.append(HumanMessage(content=r.content))
            else:
                messages.append(AIMessage(content=r.content))
        return messages

    async def _save_message(self, db: AsyncSession, role: str, content: str):
        """将一条消息写入 DB"""
        record = ChatMessageRecord(
            user_id=self.user_id,
            role=role,
            content=content,
        )
        db.add(record)
        await db.commit()

    def _build_base_prompt(self, context: dict) -> str:
        """训练上下文基础提示"""
        exercise = context.get("current_exercise", "训练")
        completed = context.get("completed_sets", 0)
        total = context.get("total_sets", 0)
        return (
            f"你是用户的AI健身搭子，亲切、鼓励、专业。"
            f"当前训练动作：{exercise}，已完成 {completed}/{total} 组。"
        )

    def _build_system_prompt(self, context: dict) -> str:
        """非流式接口的系统 Prompt，要求返回 JSON"""
        return (
            self._build_base_prompt(context)
            + "根据用户消息给出简短有力的教练回复（50字以内），并给出1-3个快捷操作建议。"
            '回复格式：JSON {"reply": "...", "coach_state": "guide|count|rest|complete", '
            '"suggested_actions": [...]}'
        )

    def _build_stream_prompt(self, context: dict) -> str:
        """流式接口的系统 Prompt，直接输出自然语言"""
        return (
            self._build_base_prompt(context)
            + "根据用户消息给出教练回复，语气亲切、简洁有力，直接用自然语言回复，不要用 JSON 格式。"
        )

    async def chat(self, message: str, context: dict) -> CoachResponse:
        """普通对话：返回完整 JSON 响应，持久化到 DB"""
        llm = await self.factory.get_client(user_id=self.user_id, model_type="chat")

        async with AsyncSessionLocal() as db:
            history = await self._load_history(db)

            messages = [SystemMessage(content=self._build_system_prompt(context))]
            messages.extend(history)
            messages.append(HumanMessage(content=message))

            response = await llm.ainvoke(messages)

            await self._save_message(db, "user", message)
            await self._save_message(db, "assistant", response.content)

        data = self._parse_json_response(response.content)
        return CoachResponse(
            reply=data.get("reply", response.content),
            coach_state=data.get("coach_state", "guide"),
            suggested_actions=data.get("suggested_actions", ["完成一组", "换个动作", "怎么做"]),
        )

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """从 LLM 回复中提取 JSON，兼容 markdown 代码块包裹"""
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    async def stream_chat(
        self, message: str, context: dict
    ) -> AsyncIterator[str]:
        """流式对话：逐 token yield，完成后持久化到 DB"""
        llm = await self.factory.get_client(
            user_id=self.user_id, model_type="chat", streaming=True
        )

        async with AsyncSessionLocal() as db:
            history = await self._load_history(db)

            messages = [SystemMessage(content=self._build_stream_prompt(context))]
            messages.extend(history)
            messages.append(HumanMessage(content=message))

            full_response = ""
            async for chunk in llm.astream(messages):
                token = chunk.content
                full_response += token
                yield token

            await self._save_message(db, "user", message)
            await self._save_message(db, "assistant", full_response)
