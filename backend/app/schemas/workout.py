"""
运动计划相关 Pydantic 模式
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date


# ===== 请求模式 =====

class WorkoutPlanGenerateRequest(BaseModel):
    """生成运动计划请求"""
    weeks: int = Field(default=4, ge=1, le=12, description="生成周数")
    days_per_week: int = Field(default=5, ge=1, le=7, description="每周天数")


class WorkoutLogCreateRequest(BaseModel):
    """创建运动记录请求"""
    workout_date: date
    workout_type: str
    name: str
    status: str = "completed"
    duration: int = 0
    calories_burned: int = 0
    exercises_completed: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


# ===== 响应模式 =====

class ExerciseItem(BaseModel):
    """运动项目"""
    name: str
    sets: int
    reps: int
    rest_seconds: int


class DayPlan(BaseModel):
    """单日训练计划"""
    day: int
    type: str
    name: str
    duration: int
    difficulty: str
    exercises: List[ExerciseItem]


class WorkoutPlanResponse(BaseModel):
    """运动计划响应"""
    id: int
    user_id: int
    weekly_workout_days: int
    estimated_calories_burn: int
    week_plan: Dict[str, Any]
    plan_start_date: date
    plan_end_date: date
    generated_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class WorkoutLogResponse(BaseModel):
    """运动记录响应"""
    id: int
    workout_date: date
    workout_type: str
    name: str
    status: str
    duration: int
    calories_burned: int
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
