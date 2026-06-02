"""WeightRecord ORM 模型：用户每日体重打卡记录"""
import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WeightRecord(Base):
    __tablename__ = "weight_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    weight: Mapped[float] = mapped_column(Float, nullable=False, comment="体重 kg")
    recorded_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True, comment="记录日期")

    note: Mapped[str | None] = mapped_column(Text, comment="备注，如饮食/状态/围度等")

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", backref="weight_records")
