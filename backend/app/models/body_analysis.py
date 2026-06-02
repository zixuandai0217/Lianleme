"""BodyAnalysisRecord ORM 模型：体型分析历史记录（含缩略图 + 结构化结果）"""
import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.compat import JSONB
from app.core.database import Base


class BodyAnalysisRecord(Base):
    __tablename__ = "body_analysis_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    image_thumbnail: Mapped[str | None] = mapped_column(Text, comment="缩略图 base64（Pillow 压缩后）")
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="BodyAnalysisResult 完整 JSON")

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", backref="body_analysis_records")
