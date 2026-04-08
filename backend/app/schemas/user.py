"""用户相关 Pydantic Schema"""
from typing import Optional

from pydantic import BaseModel, Field


class WechatLoginRequest(BaseModel):
    """微信登录请求：前端传入临时 code"""
    code: str = Field(..., description="微信 wx.login() 获得的临时 code")


class LoginResponse(BaseModel):
    """登录响应：返回 token + 用户基本信息"""
    token: str
    user_id: int
    is_new_user: bool = False


class UserProfile(BaseModel):
    """用户健身档案"""
    height: Optional[float] = Field(None, description="身高 cm")
    weight: Optional[float] = Field(None, description="体重 kg")
    goal: Optional[str] = Field(None, description="健身目标：减脂/增肌/塑形/提升体能")
    experience: Optional[str] = Field(None, description="训练经验：新手/初级/中级/高级")
    age: Optional[int] = None
    gender: Optional[str] = None


class UserProfileUpdateRequest(BaseModel):
    """用户档案更新请求"""
    nickname: Optional[str] = None
    profile: Optional[UserProfile] = None


class ApiKeyConfigRequest(BaseModel):
    """用户配置自己的 LLM API Key"""
    provider: str = Field(..., description="提供商：openai / qwen")
    api_key: str = Field(..., min_length=10, description="用户的 API Key")


class ApiKeyStatusResponse(BaseModel):
    """API Key 状态查询响应（仅返回掩码，不返回明文）"""
    has_key: bool
    provider: Optional[str] = None
    masked_key: Optional[str] = Field(None, description="掩码展示，如 'sk-...****abcd'")


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    openid: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    profile: Optional[dict] = None
    body_analysis: Optional[dict] = None
    api_key_status: Optional[ApiKeyStatusResponse] = None

    class Config:
        from_attributes = True
