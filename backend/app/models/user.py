"""
用户模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """用户基础信息表"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    openid = Column(String(64), unique=True, index=True, comment="微信/系统用户 ID")
    username = Column(String(50), unique=True, index=True, nullable=True, comment="用户名")
    nickname = Column(String(50), nullable=True, comment="昵称")
    avatar_url = Column(String(500), nullable=True, comment="头像 URL")
    gender = Column(Integer, default=0, comment="性别：0-未知 1-男 2-女")
    birthday = Column(Date, nullable=True, comment="生日")
    phone = Column(String(20), nullable=True, comment="手机号")

    # 关联当前生效的身体数据
    current_profile_id = Column(Integer, nullable=True, comment="当前生效身体数据 ID")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    profiles = relationship("Profile", back_populates="user", cascade="all, delete-orphan")
    diet_plans = relationship("DietPlan", back_populates="user", cascade="all, delete-orphan")
    workout_plans = relationship("WorkoutPlan", back_populates="user", cascade="all, delete-orphan")
    diet_logs = relationship("DietLog", back_populates="user", cascade="all, delete-orphan")
    workout_logs = relationship("WorkoutLog", back_populates="user", cascade="all, delete-orphan")
    daily_stats = relationship("DailyStat", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
