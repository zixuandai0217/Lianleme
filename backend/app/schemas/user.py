"""
用户相关 Pydantic 模式
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime, date


# ===== 请求模式 =====

class UserLoginRequest(BaseModel):
    """用户登录请求（简化登录：手机号 + 验证码）"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    code: str = Field(..., min_length=4, max_length=6, description="验证码")


class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    code: str = Field(..., min_length=4, max_length=6, description="验证码")
    nickname: Optional[str] = Field(None, max_length=50, description="昵称")


class UserProfileUpdateRequest(BaseModel):
    """用户资料更新请求"""
    nickname: Optional[str] = Field(None, max_length=50, description="昵称")
    avatar_url: Optional[str] = Field(None, max_length=500, description="头像 URL")
    gender: Optional[int] = Field(None, ge=0, le=2, description="性别")
    birthday: Optional[date] = Field(None, description="生日")


# ===== 响应模式 =====

class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    openid: Optional[str] = None
    username: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    gender: int = 0
    birthday: Optional[date] = None
    phone: Optional[str] = None
    current_profile_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    """用户完整信息响应（含身体数据）"""
    user: UserResponse
    current_profile: Optional["ProfileResponse"] = None

    class Config:
        from_attributes = True


# 前向引用
from app.schemas.profile import ProfileResponse
