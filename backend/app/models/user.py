"""User ORM 模型：用户档案 + 体型分析结果 + 用户自配置 LLM Key"""
import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # 用户基础档案（昵称、头像等微信信息）
    nickname: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(Text)

    # 用户健身档案（身高cm、体重kg、目标、训练经验）
    profile: Mapped[dict | None] = mapped_column(JSONB, comment="身高/体重/目标/训练经验等档案信息")

    # 体型分析结果（最近一次）
    body_analysis: Mapped[dict | None] = mapped_column(JSONB, comment="体型识别结果：体型/体脂/弱势肌群等")

    # 用户自配置 LLM API Key（AES-256 加密存储）
    llm_provider: Mapped[str | None] = mapped_column(
        String(16), comment="用户选择的 LLM 提供商：openai / qwen"
    )
    llm_api_key: Mapped[str | None] = mapped_column(
        Text, comment="用户自有 API Key，AES-256 加密存储"
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
