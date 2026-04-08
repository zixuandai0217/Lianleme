"""AI 陪练对话相关 Pydantic Schema"""
from typing import Optional

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
