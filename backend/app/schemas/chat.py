"""
AI 聊天相关 Pydantic 模式
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ===== 请求模式 =====

class ChatMessageRequest(BaseModel):
    """聊天消息请求"""
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., min_length=1, max_length=2000, description="消息内容")


class ChatContext(BaseModel):
    """聊天上下文"""
    calories_in: int = 0
    calories_out: int = 0
    workout_status: str = "未完成"
    diet_status: str = "未完成"


# ===== 响应模式 =====

class ChatMessageItem(BaseModel):
    """聊天消息项"""
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    """聊天响应"""
    reply: str
    session_id: str
    message_id: int


class ChatSessionResponse(BaseModel):
    """聊天会话响应"""
    session_id: str
    last_message: str
    last_message_time: datetime
    message_count: int
