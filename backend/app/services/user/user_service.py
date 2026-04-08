"""
UserService：用户档案 CRUD + 微信登录 code2session
"""
import time
from typing import Optional

import httpx
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.user import LoginResponse, UserProfileUpdateRequest


class UserService:
    """用户核心服务：微信登录、档案管理、体型结果存储"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(self, code: str) -> LoginResponse:
        """微信登录：code → openid，首次自动建档"""
        openid = await self._code2session(code)
        result = await self.db.execute(select(User).where(User.openid == openid))
        user = result.scalar_one_or_none()
        is_new = False
        if not user:
            user = User(openid=openid)
            self.db.add(user)
            await self.db.flush()
            is_new = True
        token = self._generate_token(user.id)
        return LoginResponse(token=token, user_id=user.id, is_new_user=is_new)

    async def get_user(self, user_id: int) -> Optional[User]:
        """根据 ID 获取用户"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def update_profile(
        self, user_id: int, req: UserProfileUpdateRequest
    ) -> Optional[User]:
        """更新用户健身档案"""
        user = await self.get_user(user_id)
        if not user:
            return None
        if req.nickname is not None:
            user.nickname = req.nickname
        if req.profile is not None:
            user.profile = req.profile.model_dump(exclude_none=True)
        await self.db.flush()
        return user

    async def save_body_analysis(self, user_id: int, analysis: dict) -> None:
        """保存最新体型分析结果到用户档案"""
        user = await self.get_user(user_id)
        if user:
            user.body_analysis = analysis
            await self.db.flush()

    async def _code2session(self, code: str) -> str:
        """调用微信 code2session 接口换取 openid"""
        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": settings.WECHAT_APP_ID,
            "secret": settings.WECHAT_APP_SECRET,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
        if "openid" not in data:
            raise ValueError(f"微信登录失败：{data.get('errmsg', '未知错误')}")
        return data["openid"]

    def _generate_token(self, user_id: int) -> str:
        """生成简单 JWT Token（有效期 30 天）"""
        payload = {
            "sub": str(user_id),
            "exp": int(time.time()) + 30 * 24 * 3600,
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
