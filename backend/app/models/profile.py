"""
身体数据模型
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Profile(Base):
    """用户身体数据记录表"""

    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 基础数据
    height = Column(Float, nullable=False, comment="身高 cm")
    weight = Column(Float, nullable=False, comment="体重 kg")
    body_fat_rate = Column(Float, nullable=True, comment="体脂率 %")
    muscle_mass = Column(Float, nullable=True, comment="肌肉量 kg")
    bmi = Column(Float, nullable=True, comment="BMI 指数")

    # 目标设置
    target_weight = Column(Float, nullable=True, comment="目标体重 kg")
    target_body_fat = Column(Float, nullable=True, comment="目标体脂率 %")
    weekly_goal = Column(Float, default=0.5, comment="每周目标减重 kg")
    goal_type = Column(String(20), default="lose_weight", comment="目标类型：lose_weight/gain_muscle/maintain")

    # 活动水平
    activity_level = Column(String(20), default="moderate", comment="活动水平")
    exercise_days_per_week = Column(Integer, default=3, comment="每周运动天数")

    # 健康信息
    health_issues = Column(JSON, nullable=True, comment="健康问题/禁忌")
    allergies = Column(JSON, nullable=True, comment="食物过敏")
    preferences = Column(JSON, nullable=True, comment="饮食偏好")

    # 记录时间
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), comment="记录时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="profiles")
