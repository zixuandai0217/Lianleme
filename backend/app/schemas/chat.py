"""AI 陪练对话相关 Pydantic Schema"""
import datetime
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

# ── 陪练事件流协议（v1，形状见 coach-stream-protocol spec 第 1 节）──

COACH_PROTOCOL_VERSION = 1

CoachStateName = Literal["guide", "count", "rest", "complete"]
CoachErrorCode = Literal["provider_unavailable", "rate_limited", "upstream_timeout", "internal"]
CoachFinishReason = Literal["complete", "error", "truncated"]


class CoachAction(BaseModel):
    """One quick action offered under a coach reply."""

    label: str = Field(..., min_length=1, max_length=40, description="按钮文案")
    prompt: str = Field(..., min_length=1, max_length=200, description="点击后发送的文本")


class CoachTurnStartedEvent(BaseModel):
    """首帧：协议版本与轮次标识。"""

    type: Literal["turn_started"] = "turn_started"
    protocol: int = COACH_PROTOCOL_VERSION
    turn_id: str
    message_id: str


class CoachMessageChunkEvent(BaseModel):
    """正文增量帧：用户可见正文只来自这一类事件。"""

    type: Literal["message_chunk"] = "message_chunk"
    text: str = Field(..., min_length=1)


class CoachStateEvent(BaseModel):
    """教练状态帧：可多次出现，最后一次生效。"""

    type: Literal["state"] = "state"
    coach_state: CoachStateName


class CoachActionsEvent(BaseModel):
    """快捷动作帧：一轮最多一次，且必须早于 done 帧。"""

    type: Literal["actions"] = "actions"
    actions: List[CoachAction] = Field(default_factory=list, max_length=4)


class CoachErrorEvent(BaseModel):
    """错误帧：不是终结帧，必须由 done(finish_reason="error") 收尾。"""

    type: Literal["error"] = "error"
    code: CoachErrorCode
    message: str = Field(..., min_length=1)


class CoachDoneEvent(BaseModel):
    """收尾帧：每轮唯一，且为末帧。"""

    type: Literal["done"] = "done"
    finish_reason: CoachFinishReason


CoachStreamEvent = Union[
    CoachTurnStartedEvent,
    CoachMessageChunkEvent,
    CoachStateEvent,
    CoachActionsEvent,
    CoachErrorEvent,
    CoachDoneEvent,
]

# 判别字段放在 JSON 的 type 上，客户端只有一条解析路径（不使用 SSE event: 字段）
CoachFrameEvent = Annotated[CoachStreamEvent, Field(discriminator="type")]


def sse_frame(event: CoachStreamEvent) -> str:
    """Serialize one event as a single-line ``data:`` frame.

    JSON serialization escapes newlines, so one frame can never be split by the
    client's line-based reader.
    """
    return f"data: {event.model_dump_json()}\n\n"


class ChatMessage(BaseModel):
    """用户发送的聊天消息"""
    user_id: int
    message: str = Field(..., description="用户消息内容")
    # 当前训练上下文
    current_exercise: Optional[str] = Field(None, description="当前动作名称")
    completed_sets: Optional[int] = Field(None, description="已完成组数")
    total_sets: Optional[int] = Field(None, description="总组数")
    plan_id: Optional[int] = Field(None, description="当前训练计划 ID")


class CoachResponse(BaseModel):
    """AI 教练响应（非流式）"""
    reply: str = Field(..., description="AI 教练回复内容")
    coach_state: str = Field(default="guide", description="教练当前状态节点")
    suggested_actions: list[str] = Field(
        default_factory=list, description="快捷操作建议，如 ['完成一组', '换个动作']"
    )


class WorkoutContextUpdate(BaseModel):
    """训练上下文更新（换动作/完成组数等）"""
    user_id: int
    plan_id: int
    current_exercise: str
    completed_sets: int
    total_sets: int


class ChatMessageResponse(BaseModel):
    """单条对话记录"""
    id: int
    role: str
    content: str
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """对话历史列表"""
    messages: List[ChatMessageResponse]
    total: int


class CoachTTSRequest(BaseModel):
    """Coach message text to synthesize as speech."""

    text: str = Field(..., min_length=1, max_length=500, description="要朗读的教练文案")


class CoachTTSStatusResponse(BaseModel):
    """Whether coach TTS is configured and callable for the current deployment."""

    available: bool
    lip_sync_available: bool


class CoachMouthCue(BaseModel):
    """One validated Rhubarb mouth shape interval."""

    start: float
    end: float
    value: Literal["A", "B", "C", "D", "E", "F", "G", "H", "X"]


class CoachAnimatedTTSResponse(BaseModel):
    """Base64 WAV audio plus its synchronized mouth animation timeline."""

    audio_base64: str
    mime_type: Literal["audio/wav"] = "audio/wav"
    duration_seconds: float
    mouth_cues: list[CoachMouthCue]
    alignment: Literal["rhubarb", "energy"]
