"""TrainingPlan ORM 模型：周计划 + 每日动作列表（JSONB 存储）"""
import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.compat import JSONB
from app.core.database import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # 计划周期（ISO 周起始日期，如 2026-04-06）
    week_start: Mapped[datetime.date] = mapped_column(nullable=False)

    # 完整的七天训练计划，存为 JSONB 数组（DailyWorkout 列表）
    weekly_plan: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="七天训练计划 JSON")

    # 计划生成依据的体型分析快照
    body_analysis_snapshot: Mapped[dict | None] = mapped_column(JSONB)

    # 整体难度系数（1.0 基准，用于动态调整）
    difficulty_factor: Mapped[float] = mapped_column(default=1.0)

    # 最近一次调整结论的引用（plan_adjustments.id）；只存引用不复制理由文本。
    # 刻意不加外键：plan_adjustments.plan_id 已经指向本表，再加反向外键会形成环，
    # 让建表/迁移顺序与 SQLite batch 模式都变复杂，而引用完整性由写入路径保证。
    latest_adjustment_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="active", comment="active/archived")

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", backref="training_plans")
