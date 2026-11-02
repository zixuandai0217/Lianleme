"""提醒投递记录：同时充当站内收件箱（工单 33）。

一张表承担两件事——幂等的投递事实与用户可见的站内通知——是刻意的：两套表会让
「发了没有」与「读了没有」两个状态互相漂移。唯一键（用户、规则、本地日期、通道）
保证重复 tick / 进程重启 / 手动重跑都只能落在同一条记录上。
"""
import datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.compat import JSONB
from app.core.database import Base

DELIVERY_STATUS_PENDING = "pending"
DELIVERY_STATUS_SENT = "sent"
DELIVERY_STATUS_FAILED = "failed"
DELIVERY_STATUS_SKIPPED = "skipped"
DELIVERY_STATUS_SUPPRESSED = "suppressed"

CHANNEL_IN_APP = "in_app"
CHANNEL_WEB_PUSH = "web_push"


class ReminderDelivery(Base):
    """一次提醒投递；``channel=in_app`` 且 ``status=sent`` 的记录即站内通知。"""

    __tablename__ = "reminder_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_code: Mapped[str] = mapped_column(String(32), nullable=False)
    local_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default=CHANNEL_IN_APP)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DELIVERY_STATUS_SENT)
    # 渲染参数摘要：title / body / target_path / 规则参数，收件箱直接从这里投影。
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 站内已读时间；null 表示未读。
    read_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "rule_code",
            "local_date",
            "channel",
            name="uq_reminder_deliveries_identity",
        ),
        Index("ix_reminder_deliveries_user_created_at", "user_id", "created_at"),
        Index("ix_reminder_deliveries_user_read_at", "user_id", "read_at"),
    )
