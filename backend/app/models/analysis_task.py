"""Persistent body-analysis task execution facts."""
import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.compat import JSONB
from app.core.database import Base


class AnalysisTask(Base):
    """A durable analysis request and its externally visible state."""

    __tablename__ = "analysis_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 旧字段仅为兼容既有数据保留；新任务只引用媒体资产，绝不写入图片内容。
    input_image_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    thumbnail_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    history_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("body_analysis_records.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user = relationship("User")
    history_record = relationship("BodyAnalysisRecord", foreign_keys=[history_record_id])

    __table_args__ = (
        Index("ix_analysis_tasks_user_created_at", "user_id", "created_at"),
        Index("ix_analysis_tasks_status_created_at", "status", "created_at"),
        Index("ix_analysis_tasks_lease_expires_at", "lease_expires_at"),
    )
