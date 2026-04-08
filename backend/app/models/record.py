"""WorkoutRecord ORM 模型：每次打卡训练的完成数据"""
import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WorkoutRecord(Base):
    __tablename__ = "workout_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("training_plans.id", ondelete="SET NULL"))

    # 训练日期
    workout_date: Mapped[datetime.date] = mapped_column(nullable=False, index=True)

    # 训练数据
    total_sets: Mapped[int] = mapped_column(Integer, default=0, comment="计划总组数")
    completed_sets: Mapped[int] = mapped_column(Integer, default=0, comment="实际完成组数")
    completion_rate: Mapped[float] = mapped_column(Float, default=0.0, comment="完成率 0-1")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="训练时长（分钟）")

    # 用户自评难度（1-5）
    difficulty_rating: Mapped[int | None] = mapped_column(Integer)

    # 详细完成数据（各动作完成情况）
    detail: Mapped[dict | None] = mapped_column(JSONB)

    # AI 训练后分析建议
    ai_feedback: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", backref="workout_records")
