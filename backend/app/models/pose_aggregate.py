"""姿态质量聚合：跨会话唯一被持久化的姿态数据（工单 43）。

关键点是生物特征，只在会话内存里短暂停留；训练结束后只保留这一行数值摘要：
周期计数、平均质量分、问题类型直方图与模型调用次数。这里刻意不存关键点、
坐标、帧、角度序列或可还原到单次动作实例的明细，用户可随时删除自己的聚合。

``session_id`` 唯一：结束会话重复提交只返回同一行，不产生第二次写入。
"""

import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.compat import JSONB
from app.core.database import Base


class PoseQualityAggregate(Base):
    """一次姿态训练会话的数值聚合（全流程唯一的姿态持久化事实）。"""

    __tablename__ = "pose_quality_aggregates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 不透明会话标识；唯一约束保证重复结束幂等，不重复落行。
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # 会话墙钟起止时间：用于「最近 N 天」摘要与用户可读的训练历史。
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    cycles_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluable_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_evaluable_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 问题类型 -> 命中次数；只有类型名与计数，没有关节、坐标或单次动作明细。
    issues_histogram: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
