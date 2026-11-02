"""调整结论：一次调整一条、带稳定标识（工单 08 的最小契约）。

打卡触发的 AdjustGraph 原来只把改完的动作列表写回计划，方向与理由在出口被丢弃，
于是「计划为什么变了」无法从数据回答。这张表把已有结论变成可读事实；计划侧只保存
最近一次的引用（``training_plans.latest_adjustment_id``），不复制理由文本。

该记录刻意只存「结论」：五维明细、合并分与 HITL 状态属于后续调整作业（工单 26/27），
届时在其上扩展，不在这里预埋。
"""
import datetime
import time
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# 与 AdjustGraph 的 adjustment_type 对齐；也是对外稳定枚举。
ADJUSTMENT_DIRECTIONS = ("increase", "decrease", "keep")


def new_adjustment_id() -> str:
    """Generate a time-ordered, non-guessable public identifier.

    ``adj_`` + 16 hex chars of nanosecond time + 8 random hex chars (28 chars total).
    Time prefix keeps ``ORDER BY id`` aligned with creation order, so two adjustments
    written in the same second still have a deterministic "latest" (SQLite's
    ``CURRENT_TIMESTAMP`` has second precision).
    """
    return f"adj_{time.time_ns():016x}{uuid4().hex[:8]}"


class PlanAdjustment(Base):
    """一次已落地的计划调整结论。"""

    __tablename__ = "plan_adjustments"

    # 对外稳定标识（adj_<hex>），下游引用它而不是自增主键，便于跨库/跨服务传递。
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    completion_rate: Mapped[float] = mapped_column(Float, nullable=False)
    difficulty_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user = relationship("User")
    plan = relationship("TrainingPlan")

    __table_args__ = (
        Index("ix_plan_adjustments_user_created_at", "user_id", "created_at"),
        Index("ix_plan_adjustments_plan_created_at", "plan_id", "created_at"),
    )
