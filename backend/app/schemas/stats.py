"""
统计数据相关 Pydantic 模式
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date


# ===== 响应模式 =====

class DailyStatResponse(BaseModel):
    """每日统计响应"""
    stat_date: date
    calories_in: int
    protein_in: float
    carbs_in: float
    fat_in: float
    water_ml: int
    calories_out: int
    exercise_calories: int
    steps: int
    net_calories: int
    diet_plan_completed: bool
    workout_completed: bool
    weight: Optional[float] = None
    body_fat_rate: Optional[float] = None

    class Config:
        from_attributes = True


class SummaryStatsResponse(BaseModel):
    """汇总统计响应"""
    # 周期
    start_date: date
    end_date: date

    # 平均数据
    avg_calories_in: float
    avg_calories_out: float
    avg_net_calories: float

    # 完成度
    total_days: int
    diet_completed_days: int
    workout_completed_days: int

    # 身体变化
    start_weight: Optional[float] = None
    end_weight: Optional[float] = None
    weight_change: Optional[float] = None


class WeightTrendItem(BaseModel):
    """体重趋势项"""
    date: date
    weight: float
    body_fat_rate: Optional[float] = None


class WeightTrendResponse(BaseModel):
    """体重趋势响应"""
    data: List[WeightTrendItem]
    trend: str  # "down", "up", "stable"
