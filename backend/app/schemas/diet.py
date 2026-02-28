"""
饮食计划相关 Pydantic 模式
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date


# ===== 请求模式 =====

class DietPlanGenerateRequest(BaseModel):
    """生成饮食计划请求"""
    days: int = Field(default=7, ge=1, le=30, description="生成天数")


class DietLogCreateRequest(BaseModel):
    """创建饮食记录请求"""
    log_date: date
    meal_type: str = Field(..., description="餐类型：breakfast/lunch/dinner/snack")
    foods: List[Dict[str, Any]] = Field(..., description="食物列表")
    image_url: Optional[str] = None
    notes: Optional[str] = None


# ===== 响应模式 =====

class FoodItem(BaseModel):
    """食物项"""
    name: str
    grams: Optional[int] = None
    calories: float
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None


class MealPlan(BaseModel):
    """餐次计划"""
    calories: int
    foods: List[FoodItem]


class DietPlanResponse(BaseModel):
    """饮食计划响应"""
    id: int
    user_id: int
    daily_calories: int
    protein: float
    carbohydrates: float
    fat: float
    water: int
    meals: Dict[str, Any]
    plan_date: date
    generated_by: str

    class Config:
        from_attributes = True


class DietLogResponse(BaseModel):
    """饮食记录响应"""
    id: int
    log_date: date
    meal_type: str
    foods: List[Dict[str, Any]]
    total_calories: int
    total_protein: float
    total_carbs: float
    total_fat: float
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
