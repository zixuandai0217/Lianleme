"""AI 陪练对话相关 Pydantic Schema"""
import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


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
