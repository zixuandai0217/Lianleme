"""ChatMessageRecord ORM 模型：AI 陪练对话持久化记录"""
import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.compat import JSONB
from app.core.database import Base


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="user / assistant")
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 助手消息的动作快照与教练状态：写入时由确定性规划器算好，历史回放直接投影，
    # 不在读取时重新规划（否则历史按钮会随训练上下文漂移）。旧记录两列为空。
    actions: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="[{label, prompt}] 快捷动作快照"
    )
    coach_state: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="guide / count / rest / complete"
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", backref="chat_messages")
