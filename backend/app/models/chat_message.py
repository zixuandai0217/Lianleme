"""
聊天消息模型
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ChatMessage(Base):
    """聊天消息表"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 会话 ID
    session_id = Column(String(64), nullable=False, index=True, comment="会话 ID")

    # 消息角色
    role = Column(String(20), nullable=False, comment="角色：user/assistant/system")

    # 消息内容
    content = Column(Text, nullable=False, comment="消息内容")

    # 上下文数据（今日摄入、运动等）
    context = Column(JSON, nullable=True, comment="上下文数据")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="chat_messages")
