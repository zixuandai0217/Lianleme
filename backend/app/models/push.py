"""Web Push 重通道的持久实体：浏览器订阅与待执行推送作业（工单 35）。

重通道与轻通道（站内收件箱）的分界和 tick 边界一致：tick 只写一条
``reminder_deliveries(channel=web_push, status=pending)`` 与一条 ``push_jobs``，
真正的网络发送、超时与重试都归执行器。订阅失效（推送服务返回 404/410）只把
``push_subscriptions.is_active`` 置否，后续 tick 不再为它生成新作业。
"""

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 作业状态：pending（待执行）/ sent（已发送）/ failed（终态失败）。
PUSH_JOB_STATUS_PENDING = "pending"
PUSH_JOB_STATUS_SENT = "sent"
PUSH_JOB_STATUS_FAILED = "failed"

# 订阅失效的稳定原因（只记原因码，不记录推送服务返回的原文）。
SUBSCRIPTION_FAILURE_ENDPOINT_GONE = "endpoint_gone"


class PushSubscription(Base):
    """一台浏览器/设备的推送订阅；``endpoint`` 是跨用户的唯一身份。"""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 浏览器推送服务下发的 endpoint 是长 URL，用 Text；唯一索引保证重复登记只落一行。
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_success_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_push_subscriptions_endpoint", "endpoint", unique=True),
    )


class PushJob(Base):
    """一条待执行的推送作业；一个投递记录最多对应一条作业（唯一键兜底）。"""

    __tablename__ = "push_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 一个投递记录只允许一条作业：唯一索引是幂等契约在作业侧的物理保证。
    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("reminder_deliveries.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 租约：执行器先用条件 UPDATE 抢占（claimed_at），发送完成/失败后清空；
    # 进程崩溃留下的旧租约会在下一轮被回收，避免多实例重复发送同一批。
    claimed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PUSH_JOB_STATUS_PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 只存安全摘要（如 http_410 / timeout / subscription_inactive），不存订阅密钥。
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_push_jobs_delivery_id", "delivery_id", unique=True),
        Index("ix_push_jobs_status_created_at", "status", "created_at"),
    )
