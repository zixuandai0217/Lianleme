"""媒体资产 ORM 模型：只存对象 key 与元数据，绝不存图片内容或签名 URL。"""
import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# 资产种类：本票只产生原图，缩略图由后续工单生成。
ASSET_KIND_ORIGINAL = "original"
ASSET_KIND_THUMBNAIL = "thumbnail"

# 资产状态：可用 / 已降级 / 待清理 / 已删除。
ASSET_STATUS_AVAILABLE = "available"
ASSET_STATUS_DEGRADED = "degraded"
ASSET_STATUS_PENDING_DELETE = "pending_delete"
ASSET_STATUS_DELETED = "deleted"

# 去重键只在「可用原图」上唯一：资产被标记删除后状态离开 available，
# 同一文件可以重新上传，不会撞上历史资产的唯一约束。
AVAILABLE_ORIGINAL_PREDICATE = "kind = 'original' AND status = 'available'"


class MediaAsset(Base):
    """一次上传形成的媒体资产，内容存放在对象存储。"""

    __tablename__ = "media_assets"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ASSET_KIND_ORIGINAL)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ASSET_STATUS_AVAILABLE, index=True
    )
    # 原始文件名只作为元数据保留，绝不参与对象 key 拼接。
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("User")

    __table_args__ = (
        Index(
            "ux_media_assets_user_checksum",
            "user_id",
            "checksum",
            unique=True,
            postgresql_where=text(AVAILABLE_ORIGINAL_PREDICATE),
            sqlite_where=text(AVAILABLE_ORIGINAL_PREDICATE),
        ),
    )
