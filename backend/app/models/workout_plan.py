"""
运动计划模型
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class WorkoutPlan(Base):
    """运动计划表"""

    __tablename__ = "workout_plans"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 计划概览
    weekly_workout_days = Column(Integer, default=5, comment="每周运动天数")
    estimated_calories_burn = Column(Integer, default=300, comment="单次预计消耗 kcal")

    # 每周训练计划 (JSON 格式)
    week_plan = Column(JSON, nullable=False, comment="每周训练计划")

    # 计划周期
    plan_start_date = Column(Date, nullable=False, comment="计划开始日期")
    plan_end_date = Column(Date, nullable=False, comment="计划结束日期")

    # 生成方式
    generated_by = Column(String(20), default="AI", comment="生成方式：AI/manual")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="workout_plans")


class WorkoutPlanExercise(Base):
    """运动计划动作库（可选扩展表）"""

    __tablename__ = "workout_plan_exercises"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="动作名称")
    name_en = Column(String(100), nullable=True, comment="英文名称")
    category = Column(String(50), default="strength", comment="分类：strength/cardio/flexibility")
    difficulty = Column(String(20), default="beginner", comment="难度：beginner/intermediate/advanced")
    description = Column(Text, nullable=True, comment="动作描述")
    video_url = Column(String(500), nullable=True, comment="演示视频 URL")
    thumbnail_url = Column(String(500), nullable=True, comment="缩略图 URL")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
