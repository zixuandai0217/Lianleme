"""训练计划相关 Pydantic Schema"""
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Exercise(BaseModel):
    """单个训练动作"""
    name: str = Field(..., description="动作名称，如 '卧推'")
    sets: int = Field(..., ge=1, description="组数")
    reps: str = Field(..., description="次数或时长，如 '8-12' 或 '30s'")
    weight_suggestion: str = Field(..., description="重量建议，如 '体重 40%'")
    tips: str = Field(..., description="动作要领简述")
    rest_seconds: int = Field(default=60, description="组间休息秒数")


class DailyWorkout(BaseModel):
    """单日训练计划"""
    day: int = Field(..., ge=1, le=7, description="周几 1-7")
    focus: str = Field(..., description="训练重点，如 '胸背'")
    exercises: List[Exercise]
    estimated_duration: int = Field(..., description="预计时长（分钟）")
    is_rest_day: bool = Field(default=False, description="是否休息日")


class TrainingPlanSchema(BaseModel):
    """完整周训练计划"""
    id: Optional[int] = None
    user_id: int
    week_start: datetime.date
    weekly_plan: List[DailyWorkout]
    difficulty_factor: float = 1.0
    status: str = "active"


class GeneratePlanRequest(BaseModel):
    """生成训练计划请求"""
    user_id: int
    body_analysis: Optional[dict] = None
    profile: Optional[dict] = None
    week_start: Optional[datetime.date] = None


class PlanResponse(BaseModel):
    """训练计划响应"""
    plan: TrainingPlanSchema
    message: str = "训练计划生成成功"
