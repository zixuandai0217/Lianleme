"""
饮食计划模型
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class DietPlan(Base):
    """饮食计划表"""

    __tablename__ = "diet_plans"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)

    # 营养目标
    daily_calories = Column(Integer, nullable=False, comment="每日热量目标 kcal")
    protein = Column(Float, nullable=False, comment="蛋白质 g")
    carbohydrates = Column(Float, nullable=False, comment="碳水 g")
    fat = Column(Float, nullable=False, comment="脂肪 g")
    water = Column(Integer, default=2000, comment="饮水 ml")

    # 餐次分配 (JSON 格式存储早中晚三餐详情)
    meals = Column(JSON, nullable=False, comment="餐次分配")

    # 饮食偏好
    preferences = Column(JSON, nullable=True, comment="饮食偏好")
    avoid_foods = Column(JSON, nullable=True, comment="避免食物")

    # 计划日期
    plan_date = Column(Date, nullable=False, index=True, comment="计划日期")
    generated_by = Column(String(20), default="AI", comment="生成方式：AI/manual")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="diet_plans")
