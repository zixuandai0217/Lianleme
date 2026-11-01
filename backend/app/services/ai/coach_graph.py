"""
CoachGraph：AI 陪练对话引擎
对话历史持久化到 DB（chat_messages 表），LLM 上下文取最近 20 条

模型输出在离开服务端之前统一清洗（见 CoachTextCleaner）：JSON 外壳、代码围栏、
结构化残留不进入用户可见文本，入库的是清洗后的正文，因此历史回放与实时一致。
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

# 清洗后整轮没有可读内容时发送的兜底文案（短句、西海岸口气、不含脏话）
COACH_FALLBACK_REPLY = "刚才那段我卡了一下，homie，再跟我说一遍，我接着带。"

REPLY_FIELD_NAMES = ("reply", "message", "content")

_FENCE = "```"
_HEAD_JSON_LIMIT = 2048
_FENCE_LANGUAGE = re.compile(r"^[A-Za-z0-9_+-]*\s*\n")
_KEY_VALUE_RESIDUE = re.compile(
    r'"[A-Za-z_][A-Za-z0-9_]*"\s*:\s*'
    r'(?:"[^"]*"|\[[^\]]*\]|\{[^{}]*\}|-?\d+(?:\.\d+)?|true|false|null)\s*,?'
)


def _reply_text_from_payload(payload: object) -> str | None:
    """Extract the readable reply from a decoded JSON envelope, if it has one."""
    if not isinstance(payload, dict):
        return None
    for field in REPLY_FIELD_NAMES:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _json_is_balanced(text: str) -> bool:
    """Whether quotes and brackets are balanced, i.e. further input could close it."""
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


def _decode_json_prefix(text: str) -> tuple[object | None, int]:
    """Decode one leading JSON value, returning (value, consumed characters)."""
    try:
        value, consumed = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return None, 0
    return value, consumed


def _prose_after_structure(text: str) -> str:
    """Return the part following the last closing bracket of a broken envelope."""
    last = max(text.rfind("}"), text.rfind("]"))
    return text[last + 1:] if last >= 0 else ""


def _strip_inline_residue(text: str) -> str:
    """Remove inline structural residue so it never reaches the bubble."""
    text = text.replace("`", "")
    text = text.replace('{"', "").replace('"}', "")
    return _KEY_VALUE_RESIDUE.sub("", text)


def _held_tail_length(text: str) -> int:
    """Trailing characters kept buffered because they may start a marker."""
    for size in (2, 1):
        if text[-size:] in ("``", "`", '{"', '"}', "{", '"'):
            return size
    return 0


def _fenced_reply(inner: str) -> str:
    """A fenced block only contributes text when it carries a JSON reply field."""
    text = inner.strip()
    if not text:
        return ""
    text = _FENCE_LANGUAGE.sub("", text, count=1)
    payload, _consumed = _decode_json_prefix(text)
    return _reply_text_from_payload(payload) or ""


class CoachTextCleaner:
    """Turn raw coach model output into user-visible text (spec §2).

    Streaming and order preserving: text is released as soon as it is known not to
    belong to a JSON envelope or a code fence, and released text is never retracted.
    Fenced blocks and JSON wrappers never reach the bubble.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._mode = "head"
        self._fence = ""
        self._pending = ""
        self._released = False

    def feed(self, chunk: str) -> str:
        """Consume one model delta and return the text that can be shown now."""
        if not chunk:
            return ""
        self._buffer += chunk
        return self._release(self._drain(final=False), final=False)

    def flush(self) -> str:
        """Release whatever is still buffered when the model stops producing."""
        return self._release(self._drain(final=True), final=True)

    def _release(self, text: str, final: bool) -> str:
        """Hold whitespace until readable text follows, so no frame is ever empty."""
        if not text:
            return ""
        self._pending += text
        if not self._pending.strip():
            if final:
                self._pending = ""
            return ""
        released, self._pending = self._pending, ""
        if not self._released:
            released = released.lstrip()
            if not released:
                return ""
            self._released = True
        return released

    def _drain(self, final: bool) -> str:
        out: list[str] = []
        while self._buffer:
            if self._mode == "fence":
                if not self._consume_fence(out, final):
                    break
            elif self._mode == "head":
                if not self._decide_head(final):
                    break
            elif self._mode == "json":
                if not self._consume_envelope(out, final):
                    break
            elif not self._consume_text(out, final):
                break
        return "".join(out)

    def _decide_head(self, final: bool) -> bool:
        """Decide whether the leading characters are a JSON envelope or plain prose."""
        stripped = self._buffer.lstrip()
        if not stripped:
            if final:
                self._buffer = ""
            return False
        if not final and len(stripped) < len(_FENCE) and _FENCE.startswith(stripped):
            return False  # a fence marker may still be split across deltas
        if len(stripped) < 2 and not final:
            return False
        self._buffer = stripped
        if stripped.startswith(_FENCE):
            self._buffer = stripped[len(_FENCE):]
            self._fence = ""
            self._mode = "fence"
            return True
        if stripped[0] in "{[":
            self._mode = "json"
            return True
        self._mode = "text"
        return True

    def _consume_envelope(self, out: list[str], final: bool) -> bool:
        """Decode the opening JSON envelope and keep its reply field, if any."""
        text = self._buffer
        payload, consumed = _decode_json_prefix(text)
        if payload is not None:
            self._buffer = text[consumed:]
            reply = _reply_text_from_payload(payload)
            if reply:
                out.append(reply)
            self._mode = "text"
            return True
        if not final and not _json_is_balanced(text) and len(text) < _HEAD_JSON_LIMIT:
            return False  # the envelope is still open, wait for more deltas
        if _json_is_balanced(text):
            # Balanced but undecodable: drop the structure, keep the prose after it.
            self._buffer = _prose_after_structure(text)
            self._mode = "text"
            return bool(self._buffer)
        # Unterminated or oversized envelope: nothing readable to release.
        self._buffer = ""
        self._mode = "text"
        return False

    def _consume_text(self, out: list[str], final: bool) -> bool:
        """Release plain prose until a code fence opens."""
        buffer = self._buffer
        fence_at = buffer.find(_FENCE)
        if fence_at >= 0:
            head = buffer[:fence_at]
            if head:
                out.append(_strip_inline_residue(head))
            self._buffer = buffer[fence_at + len(_FENCE):]
            self._fence = ""
            self._mode = "fence"
            return True
        if final:
            out.append(_strip_inline_residue(buffer))
            self._buffer = ""
            return False
        held = _held_tail_length(buffer)
        if held:
            chunk, self._buffer = buffer[:-held], buffer[-held:]
        else:
            chunk, self._buffer = buffer, ""
        out.append(_strip_inline_residue(chunk))
        return False

    def _consume_fence(self, out: list[str], final: bool) -> bool:
        """Swallow a fenced block; only a JSON reply field survives it."""
        combined = self._fence + self._buffer
        closing = combined.find(_FENCE)
        if closing < 0:
            if not final:
                self._fence = combined
                self._buffer = ""
                return False
            self._fence = ""
            self._buffer = ""
            self._mode = "text"
            return False
        inner = combined[:closing]
        self._buffer = combined[closing + len(_FENCE):]
        self._fence = ""
        self._mode = "text"
        reply = _fenced_reply(inner)
        if reply:
            out.append(reply)
        return True


def clean_coach_text(text: str) -> str:
    """Clean one complete model output with the same rules as the stream cleaner."""
    cleaner = CoachTextCleaner()
    return (cleaner.feed(text) + cleaner.flush()).strip()


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
            "你是用户熟悉的高能健身房搭子，粗犷、街头、爱挑衅但始终支持用户。"
            "自然用 bro 和 homie 称呼用户；动作漂亮、冲刺或破纪录时可以喊 shit。"
            "短句重拍，夸赞和施压交替，不要每句话都堆 slang 或脏话。"
            "可以像朋友一样吼，但不攻击用户的身份、外貌或人格。"
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
        """普通对话：返回完整 JSON 响应，持久化清洗后的正文"""
        llm = await self.factory.get_client(user_id=self.user_id, model_type="chat")

        async with AsyncSessionLocal() as db:
            history = await self._load_history(db)

            messages = [SystemMessage(content=self._build_system_prompt(context))]
            messages.extend(history)
            messages.append(HumanMessage(content=message))

            response = await llm.ainvoke(messages)
            raw = response.content if isinstance(response.content, str) else ""
            data = self._parse_json_response(raw)
            payload = data if isinstance(data, dict) else {}
            reply = (
                _reply_text_from_payload(payload)
                or clean_coach_text(raw)
                or COACH_FALLBACK_REPLY
            )

            await self._save_message(db, "user", message)
            await self._save_message(db, "assistant", reply)

        return CoachResponse(
            reply=reply,
            coach_state=payload.get("coach_state", "guide"),
            suggested_actions=payload.get(
                "suggested_actions", ["完成一组", "换个动作", "怎么做"]
            ),
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
        """流式对话：逐段 yield 模型原文增量（清洗由协议层在出帧前完成）"""
        llm = await self.factory.get_client(
            user_id=self.user_id, model_type="chat", streaming=True
        )

        async with AsyncSessionLocal() as db:
            history = await self._load_history(db)

            messages = [SystemMessage(content=self._build_stream_prompt(context))]
            messages.extend(history)
            messages.append(HumanMessage(content=message))

            async for chunk in llm.astream(messages):
                token = chunk.content if isinstance(chunk.content, str) else ""
                if token:
                    yield token

    async def save_turn(self, message: str, reply: str) -> None:
        """将一轮对话入库；reply 必须是清洗后的正文，历史回放才不会泄漏结构残留"""
        async with AsyncSessionLocal() as db:
            await self._save_message(db, "user", message)
            await self._save_message(db, "assistant", reply)
