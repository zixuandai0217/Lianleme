"""
身体数据相关 Pydantic 模式
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date


# ===== 请求模式 =====

class ProfileCreateRequest(BaseModel):
    """创建身体数据请求"""
    height: float = Field(..., gt=0, le=300, description="身高 cm")
    weight: float = Field(..., gt=0, le=500, description="体重 kg")
    body_fat_rate: Optional[float] = Field(None, ge=0, le=100, description="体脂率 %")
    muscle_mass: Optional[float] = Field(None, gt=0, description="肌肉量 kg")

    # 目标设置
    target_weight: Optional[float] = Field(None, gt=0, le=500, description="目标体重 kg")
    target_body_fat: Optional[float] = Field(None, ge=0, le=100, description="目标体脂率 %")
    weekly_goal: float = Field(default=0.5, ge=0.1, le=2, description="每周目标减重 kg")
    goal_type: str = Field(default="lose_weight", description="目标类型")
    activity_level: str = Field(default="moderate", description="活动水平")
    exercise_days_per_week: int = Field(default=3, ge=0, le=7, description="每周运动天数")

    # 健康信息
    health_issues: Optional[dict] = Field(None, description="健康问题")
    allergies: Optional[List[str]] = Field(None, description="食物过敏")
    preferences: Optional[List[str]] = Field(None, description="饮食偏好")


class ProfileUpdateRequest(BaseModel):
    """更新身体数据请求"""
    height: Optional[float] = Field(None, gt=0, le=300, description="身高 cm")
    weight: Optional[float] = Field(None, gt=0, le=500, description="体重 kg")
    body_fat_rate: Optional[float] = Field(None, ge=0, le=100, description="体脂率 %")
    muscle_mass: Optional[float] = Field(None, gt=0, description="肌肉量 kg")
    target_weight: Optional[float] = Field(None, gt=0, le=500, description="目标体重 kg")
    weekly_goal: Optional[float] = Field(None, ge=0.1, le=2, description="每周目标减重 kg")
    goal_type: Optional[str] = Field(None, description="目标类型")
    activity_level: Optional[str] = Field(None, description="活动水平")


# ===== 响应模式 =====

class ProfileResponse(BaseModel):
    """身体数据响应"""
    id: int
    user_id: int
    height: float
    weight: float
    body_fat_rate: Optional[float] = None
    muscle_mass: Optional[float] = None
    bmi: Optional[float] = None
    target_weight: Optional[float] = None
    target_body_fat: Optional[float] = None
    weekly_goal: float
    goal_type: str
    activity_level: str
    exercise_days_per_week: int
    health_issues: Optional[dict] = None
    allergies: Optional[List[str]] = None
    preferences: Optional[List[str]] = None
    recorded_at: datetime

    class Config:
        from_attributes = True


class ProfileHistoryResponse(BaseModel):
    """身体数据历史列表响应"""
    total: int
    profiles: List[ProfileResponse]
