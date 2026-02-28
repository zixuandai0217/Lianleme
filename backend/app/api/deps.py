"""
API 依赖注入
"""
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import re

from app.database import get_db
from app.core.security import decode_access_token, get_token_user_id
from app.models.user import User


# HTTP Bearer Token 认证
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    获取当前登录用户

    从 Header 中提取 Token 并验证用户
    """
    # 1. 尝试从 Authorization Header 获取 token
    token = None

    if credentials:
        token = credentials.credentials
    else:
        # 2. 尝试从请求头获取
        auth_header = request.headers.get("Authorization")
        if auth_header:
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            else:
                token = auth_header

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. 解码 token 获取用户 ID
    user_id = get_token_user_id(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. 查询用户
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    return user


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    获取可选用户（不强制登录）
    """
    try:
        user = await get_current_user(request, db=db)
        return user
    except HTTPException:
        return None


def parse_pagination(page: int = 1, page_size: int = 20) -> tuple:
    """
    解析分页参数
    """
    # 限制 page_size 范围
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    offset = (page - 1) * page_size

    return page, page_size, offset
