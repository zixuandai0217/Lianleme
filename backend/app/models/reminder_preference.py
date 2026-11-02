"""提醒偏好：每个用户一条（工单 34）。

第一版只保留部署级时区（``Asia/Shanghai``），字段先留出以便后续按用户时区计算日界；
免打扰区间用 ``HH:MM`` 文本存储，跨零点由判定函数解释，避免数据库层参与时间语义。
"""
import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

DEFAULT_QUIET_HOURS_START = "22:00"
DEFAULT_QUIET_HOURS_END = "08:00"
DEFAULT_DAILY_CAP = 2
DEFAULT_WEEKLY_GOAL_TARGET = 3
DEFAULT_TIMEZONE = "Asia/Shanghai"


class ReminderPreference(Base):
    """用户提醒偏好（与用户一对一，主键即 user_id）。"""

    __tablename__ = "reminder_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # 逐类开关：关闭后该规则不再产生投递记录（其他规则不受影响）。
    daily_training_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rest_day_note_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recall_inactive_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weekly_goal_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    onboarding_nudge_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 免打扰区间（本地时间 HH:MM，可跨零点）；两端相同视为非法。
    quiet_hours_start: Mapped[str] = mapped_column(
        String(5), nullable=False, default=DEFAULT_QUIET_HOURS_START
    )
    quiet_hours_end: Mapped[str] = mapped_column(
        String(5), nullable=False, default=DEFAULT_QUIET_HOURS_END
    )
    daily_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_DAILY_CAP)
    weekly_goal_target: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_WEEKLY_GOAL_TARGET
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default=DEFAULT_TIMEZONE)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User")
