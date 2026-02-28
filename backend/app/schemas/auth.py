"""
认证相关 Pydantic 模式
"""
from typing import Optional
from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """Token 请求（微信登录）"""
    code: str = Field(..., description="微信登录 code")


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: int
    nickname: Optional[str] = None


class SimpleLoginRequest(BaseModel):
    """简化登录请求（手机号 + 验证码）"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    verify_code: str = Field(..., min_length=4, max_length=6, description="验证码")


class VerifyCodeRequest(BaseModel):
    """获取验证码请求"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
