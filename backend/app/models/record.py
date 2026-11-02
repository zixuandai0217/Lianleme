"""WorkoutRecord ORM 模型：每次打卡训练的完成数据"""
import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.compat import JSONB
from app.core.database import Base


class WorkoutRecord(Base):
    __tablename__ = "workout_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_plans.id", ondelete="SET NULL")
    )

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

    # 工单 28：打卡只保存调整作业的引用与提交时刻的状态快照。方向、理由与前后
    # 摘要不在这里复制——读取时按 job_id 投影作业与调整结论，计划解释卡与打卡
    # 反馈因此永远显示同一份事实。
    # 与 training_plans.latest_adjustment_id 一样刻意不加外键：作业表已经通过
    # user_id 指向用户，再反向加外键会让迁移/建表顺序与 SQLite batch 变复杂；
    # 引用完整性由写入路径保证，读取时作业缺失也有稳定降级。
    adjustment_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plan_impact_status: Mapped[str | None] = mapped_column(String(24), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", backref="workout_records")

    # 一天一条打卡：并发重复提交只能有一条落库（服务层幂等 + 数据库兜底）。
    __table_args__ = (
        Index("uq_workout_records_user_date", "user_id", "workout_date", unique=True),
    )
