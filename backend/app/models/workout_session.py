"""训练会话：可推进、可恢复的当日训练事实（工单 22）。

会话是独立聚合，不复用打卡记录：打卡记录代表「已完成的训练事实」，而会话需要
「进行中」这个可恢复的中间态。动作明细按「动作序号 + 组序号」定位，存在 JSONB 里，
因为它总是跟着会话整体读写，不需要单独查询/聚合；指针（当前动作、当前组）是服务端
算好的派生状态，前端不自行推算。
"""
import datetime
import time
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.compat import JSONB
from app.core.database import Base

SESSION_STATUS_IN_PROGRESS = "in_progress"
SESSION_STATUS_COMPLETED = "completed"
SESSION_STATUS_ABANDONED = "abandoned"

# 会话在「进行中」停留超过这么久没有活动，读路径会把它收敛为 abandoned。
SESSION_IDLE_HOURS = 12


def new_session_id() -> str:
    """Time-ordered public identifier (``ws_`` + ns time + randomness), like adjustments."""
    return f"ws_{time.time_ns():016x}{uuid4().hex[:8]}"


class WorkoutSession(Base):
    """一个用户的当天训练会话（同一本地日期最多一条）。"""

    __tablename__ = "workout_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_plans.id", ondelete="SET NULL"), nullable=True
    )
    # 会话归属的本地日期（开始当天）；跨零点继续训练仍算开始日。
    session_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SESSION_STATUS_IN_PROGRESS
    )

    # 服务端指针不落库：当前动作/当前组由明细派生（见会话视图），避免两套真相。
    total_sets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_sets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 动作明细：[{order, name, sets, reps, weight_suggestion, tips, rest_seconds,
    #            completed_sets, skipped, skip_reason}]
    exercises: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User")
    plan = relationship("TrainingPlan")

    __table_args__ = (
        UniqueConstraint("user_id", "session_date", name="uq_workout_sessions_user_date"),
        Index("ix_workout_sessions_user_status", "user_id", "status"),
        Index("ix_workout_sessions_user_date", "user_id", "session_date"),
    )
