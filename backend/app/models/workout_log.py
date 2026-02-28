"""
运动记录模型
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class WorkoutLog(Base):
    """运动记录表"""

    __tablename__ = "workout_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("workout_plans.id"), nullable=True)

    # 训练信息
    workout_date = Column(Date, nullable=False, index=True, comment="训练日期")
    day_number = Column(Integer, nullable=True, comment="第几天训练")
    workout_type = Column(String(50), default="cardio", comment="训练类型")
    name = Column(String(100), nullable=False, comment="训练名称")

    # 完成情况
    status = Column(String(20), default="completed", comment="状态：completed/partial/skipped")
    duration = Column(Integer, default=0, comment="实际用时 分钟")
    calories_burned = Column(Integer, default=0, comment="实际消耗 kcal")

    # 动作完成详情 (JSON 格式)
    exercises_completed = Column(JSON, nullable=True, comment="动作完成详情")

    # 心率数据（如有）
    heart_rate_avg = Column(Integer, nullable=True, comment="平均心率")
    heart_rate_max = Column(Integer, nullable=True, comment="最大心率")

    # 备注
    notes = Column(Text, nullable=True, comment="备注")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="workout_logs")
