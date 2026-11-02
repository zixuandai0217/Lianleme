"""训练计划相关 Pydantic Schema"""
import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# 今日状态的稳定枚举：前端仅凭该字段即可分叉，不再用「有没有 exercises」猜语义。
TodayWorkoutStatus = Literal["training_day", "rest_day", "no_plan"]


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


class TodayWorkoutResponse(BaseModel):
    """今日训练三态响应。

    ``status`` 是唯一判定入口：training_day 带动作清单与汇总，rest_day 带恢复文案、
    no_plan 两者都不带。旧字段（``is_rest_day`` / ``day`` / ``focus`` / ``exercises``）
    继续保留：老调用方读不到清单时自然会走空态分支，不会被误判成训练日。
    """
    status: TodayWorkoutStatus = Field(..., description="training_day / rest_day / no_plan")
    is_rest_day: bool = Field(default=False, description="是否休息日；无计划时恒为 false")
    day: Optional[int] = Field(default=None, description="周几 1-7；无计划时为空")
    focus: Optional[str] = Field(default=None, description="训练重点")
    exercises: Optional[List[Exercise]] = Field(default=None, description="仅在训练日返回")
    estimated_duration: Optional[int] = Field(default=None, description="预计时长（分钟）")
    exercise_count: Optional[int] = Field(default=None, description="动作数量（仅训练日）")
    total_sets: Optional[int] = Field(default=None, description="计划总组数（仅训练日）")
    plan_id: Optional[int] = Field(default=None, description="计划标识（有可用计划时）")
    message: Optional[str] = Field(default=None, description="休息日恢复提示；无计划时不返回")
