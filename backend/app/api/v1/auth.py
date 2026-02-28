"""
认证路由
提供简化的登录注册功能
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    SimpleLoginRequest,
    TokenResponse,
    VerifyCodeRequest
)
from app.core.security import create_access_token
from app.schemas.common import APIResponse

router = APIRouter()

# 模拟验证码存储（生产环境应使用 Redis）
_verification_codes = {}


@router.post("/verify-code", response_model=APIResponse, summary="获取验证码")
async def send_verify_code(request: VerifyCodeRequest):
    """
    发送验证码（简化实现：直接返回验证码）

    生产环境应接入短信服务
    """
    phone = request.phone

    # 生成简单的 6 位验证码
    import random
    code = str(random.randint(100000, 999999))

    # 存储验证码（5 分钟有效期）
    _verification_codes[phone] = code

    # 开发环境：在响应中返回验证码方便测试
    return APIResponse(
        message="验证码已发送",
        data={"code": code}  # 生产环境请移除此行
    )


@router.post("/login", response_model=TokenResponse, summary="登录/注册")
async def login(
    request: SimpleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    登录或注册

    使用手机号 + 验证码进行登录
    如果用户不存在则自动创建
    """
    phone = request.phone
    code = request.verify_code

    # 验证验证码
    stored_code = _verification_codes.get(phone)
    if not stored_code or stored_code != code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误"
        )

    # 查询或创建用户
    user = await db.query(User).filter(User.phone == phone).first()

    if not user:
        # 创建新用户
        user = User(
            phone=phone,
            nickname=f"用户{phone[-4:]}",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # 生成 Token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(days=7)
    )

    # 删除已使用的验证码
    del _verification_codes[phone]

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        nickname=user.nickname
    )


@router.post("/logout", response_model=APIResponse, summary="登出")
async def logout():
    """
    登出

    由于使用 JWT，服务端无需额外操作
    客户端删除本地存储的 token 即可
    """
    return APIResponse(message="登出成功")


@router.get("/me", response_model=dict, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(lambda: None)):
    """
    获取当前登录用户信息

    需要认证
    """
    # 实际实现由 deps.get_current_user 处理认证
    return {
        "id": current_user.id,
        "nickname": current_user.nickname,
        "avatar_url": current_user.avatar_url,
        "gender": current_user.gender,
        "phone": current_user.phone
    }
