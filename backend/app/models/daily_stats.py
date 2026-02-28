"""
每日统计聚合模型
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class DailyStat(Base):
    """每日统计聚合表"""

    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 统计日期
    stat_date = Column(Date, nullable=False, index=True, comment="统计日期")

    # 摄入
    calories_in = Column(Integer, default=0, comment="摄入热量 kcal")
    protein_in = Column(Float, default=0, comment="摄入蛋白质 g")
    carbs_in = Column(Float, default=0, comment="摄入碳水 g")
    fat_in = Column(Float, default=0, comment="摄入脂肪 g")
    water_ml = Column(Integer, default=0, comment="饮水 ml")

    # 消耗
    calories_out = Column(Integer, default=0, comment="消耗热量 kcal (TDEE + 运动)")
    exercise_calories = Column(Integer, default=0, comment="运动消耗 kcal")
    steps = Column(Integer, default=0, comment="步数")

    # 净值
    net_calories = Column(Integer, default=0, comment="热量缺口/盈余 kcal")

    # 计划完成度
    diet_plan_completed = Column(Boolean, default=False, comment="饮食计划完成")
    workout_completed = Column(Boolean, default=False, comment="运动计划完成")

    # 身体数据（如有记录）
    weight = Column(Float, nullable=True, comment="体重 kg")
    body_fat_rate = Column(Float, nullable=True, comment="体脂率 %")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="daily_stats")

    # 唯一约束：用户 + 日期
    __table_args__ = (
        UniqueConstraint("user_id", "stat_date", name="user_date_unique"),
    )
