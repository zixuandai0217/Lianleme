"""用户档案 CRUD、邮箱认证和开发身份服务。"""
import time
from typing import Optional

import hashlib
import os

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.user import LoginResponse, RegisterRequest, UserProfileUpdateRequest


def _hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 password hashing with random salt."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash created by _hash_password."""
    salt_hex, dk_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return dk.hex() == dk_hex


class UserService:
    """管理用户认证、档案和体型分析结果。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, req: RegisterRequest) -> LoginResponse:
        """邮箱注册：创建新用户并返回 token"""
        result = await self.db.execute(select(User).where(User.email == req.email))
        if result.scalar_one_or_none():
            raise ValueError("该邮箱已被注册")

        openid = f"email_{req.email}"
        user = User(
            openid=openid,
            email=req.email,
            password_hash=_hash_password(req.password),
            nickname=req.nickname or req.email.split("@")[0],
        )
        self.db.add(user)
        await self.db.flush()
        token = self._generate_token(user.id)
        return LoginResponse(token=token, user_id=user.id, is_new_user=True)

    async def email_login(self, email: str, password: str) -> LoginResponse:
        """邮箱登录：验证凭据并返回 token"""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user or not user.password_hash:
            raise ValueError("邮箱或密码错误")
        if not _verify_password(password, user.password_hash):
            raise ValueError("邮箱或密码错误")
        token = self._generate_token(user.id)
        return LoginResponse(token=token, user_id=user.id, is_new_user=False)

    async def dev_login(self) -> LoginResponse:
        """开发模式默认登录普通用户，兼容现有调用方。"""
        return await self.dev_user_login()

    async def dev_user_login(self) -> LoginResponse:
        """开发模式普通用户登录：查找或创建默认用户账号。"""
        return await self._dev_login_for_identity(
            openid="dev-web-user",
            nickname="My homie",
            is_admin=False,
        )

    async def dev_admin_login(self) -> LoginResponse:
        """开发模式管理员登录：查找或创建默认管理员账号。"""
        return await self._dev_login_for_identity(
            openid="dev-admin-user",
            nickname="Web 管理员",
            is_admin=True,
        )

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

    async def _dev_login_for_identity(
        self,
        *,
        openid: str,
        nickname: str,
        is_admin: bool,
    ) -> LoginResponse:
        """Create or reuse a fixed development identity with the expected role."""
        result = await self.db.execute(select(User).where(User.openid == openid))
        user = result.scalar_one_or_none()
        is_new = False
        if not user:
            user = User(openid=openid, nickname=nickname, is_admin=is_admin)
            self.db.add(user)
            await self.db.flush()
            is_new = True
        else:
            changed = False
            if user.nickname != nickname:
                user.nickname = nickname
                changed = True
            if bool(user.is_admin) != is_admin:
                user.is_admin = is_admin
                changed = True
            if changed:
                await self.db.flush()
        token = self._generate_token(user.id)
        return LoginResponse(token=token, user_id=user.id, is_new_user=is_new)

    def _generate_token(self, user_id: int) -> str:
        """生成简单 JWT Token（有效期 30 天）"""
        payload = {
            "sub": str(user_id),
            "exp": int(time.time()) + 30 * 24 * 3600,
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
