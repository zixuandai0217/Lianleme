"""训练记录相关 Pydantic Schema"""
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WorkoutCompleteRequest(BaseModel):
    """训练完成上报请求"""
    user_id: int
    plan_id: Optional[int] = None
    workout_date: datetime.date
    total_sets: int
    completed_sets: int
    duration_minutes: int
    difficulty_rating: Optional[int] = Field(None, ge=1, le=5, description="用户自评难度 1-5")
    detail: Optional[dict] = Field(None, description="各动作完成详情 JSON")


class WorkoutRecordResponse(BaseModel):
    """训练记录响应"""
    id: int
    workout_date: datetime.date
    completion_rate: float
    duration_minutes: int
    ai_feedback: Optional[str] = None

    class Config:
        from_attributes = True


class CheckInStatsResponse(BaseModel):
    """打卡统计响应"""
    total_checkins: int
    streak_days: int = Field(..., description="连续打卡天数")
    monthly_checkins: int
    monthly_completion_rate: float
    recent_records: List[WorkoutRecordResponse] = []
