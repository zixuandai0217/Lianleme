"""
ApiKeyService：用户 LLM API Key 的 AES-256 加密存取
用户自有 Key 加密后落库，读取时解密，对外只暴露掩码
"""
import base64
from typing import Optional, Tuple

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.user import ApiKeyStatusResponse


class ApiKeyService:
    """用户 API Key 的加密存取服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        # AES key 必须 32 字节
        self._aes_key = settings.AES_SECRET_KEY.encode("utf-8")[:32].ljust(32, b"\x00")

    def _encrypt(self, plaintext: str) -> str:
        """AES-256-CBC 加密，返回 base64 编码的密文"""
        cipher = AES.new(self._aes_key, AES.MODE_CBC)
        ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
        iv_b64 = base64.b64encode(cipher.iv).decode()
        ct_b64 = base64.b64encode(ct).decode()
        return f"{iv_b64}:{ct_b64}"

    def _decrypt(self, ciphertext: str) -> str:
        """AES-256-CBC 解密"""
        iv_b64, ct_b64 = ciphertext.split(":", 1)
        iv = base64.b64decode(iv_b64)
        ct = base64.b64decode(ct_b64)
        cipher = AES.new(self._aes_key, AES.MODE_CBC, iv=iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode("utf-8")

    def _mask_key(self, raw_key: str) -> str:
        """生成掩码展示：sk-...****xxxx"""
        if len(raw_key) <= 8:
            return "****"
        return raw_key[:3] + "..." + "****" + raw_key[-4:]

    async def save_key(self, user_id: int, provider: str, api_key: str) -> ApiKeyStatusResponse:
        """加密保存用户 API Key"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")
        user.llm_provider = provider
        user.llm_api_key = self._encrypt(api_key)
        await self.db.flush()
        return ApiKeyStatusResponse(
            has_key=True,
            provider=provider,
            masked_key=self._mask_key(api_key),
        )

    async def delete_key(self, user_id: int) -> ApiKeyStatusResponse:
        """清除用户 API Key，恢复使用系统默认"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.llm_provider = None
            user.llm_api_key = None
            await self.db.flush()
        return ApiKeyStatusResponse(has_key=False)

    async def get_status(self, user_id: int) -> ApiKeyStatusResponse:
        """查询 API Key 状态（仅返回掩码，不返回明文）"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.llm_api_key:
            return ApiKeyStatusResponse(has_key=False)
        try:
            raw_key = self._decrypt(user.llm_api_key)
            return ApiKeyStatusResponse(
                has_key=True,
                provider=user.llm_provider,
                masked_key=self._mask_key(raw_key),
            )
        except Exception:
            return ApiKeyStatusResponse(has_key=False)

    async def get_decrypted_key(self, user_id: int) -> Optional[Tuple[str, str]]:
        """
        内部使用：返回解密后的 (provider, api_key)，供 LLMClientFactory 调用
        不可对外暴露
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.llm_api_key:
            return None
        try:
            raw_key = self._decrypt(user.llm_api_key)
            return user.llm_provider, raw_key
        except Exception:
            return None
