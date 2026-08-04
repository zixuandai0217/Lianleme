"""
ApiKeyService：用户 LLM API Key 的 AES-256 加密存取
用户自有 Key 加密后落库，读取时解密，对外只暴露掩码
"""
import base64
import hashlib
from typing import Optional, Tuple

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.user import ApiKeyStatusResponse


class ApiKeyRequiredError(ValueError):
    """Signal that a user-owned provider key is required for an AI request."""


class ApiKeyService:
    """用户 API Key 的加密存取服务"""

    _SUPPORTED_PROVIDERS = frozenset({"openai", "qwen"})
    _GCM_PREFIX = ("v1", "gcm")

    def __init__(self, db: AsyncSession):
        self.db = db
        secret = settings.AES_SECRET_KEY.encode("utf-8")
        self._aes_key = hashlib.sha256(secret).digest()
        self._legacy_aes_key = secret[:32].ljust(32, b"\x00")

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt one provider secret with a versioned AES-256-GCM envelope."""
        cipher = AES.new(self._aes_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
        fields = (
            *self._GCM_PREFIX,
            base64.b64encode(cipher.nonce).decode(),
            base64.b64encode(tag).decode(),
            base64.b64encode(ciphertext).decode(),
        )
        return ":".join(fields)

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt authenticated GCM rows and legacy CBC rows during migration."""
        if ciphertext.startswith(":".join(self._GCM_PREFIX) + ":"):
            parts = ciphertext.split(":")
            if len(parts) != 5 or tuple(parts[:2]) != self._GCM_PREFIX:
                raise ValueError("API Key 密文格式无效")
            nonce, tag, encrypted = (
                base64.b64decode(value, validate=True) for value in parts[2:]
            )
            cipher = AES.new(self._aes_key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(encrypted, tag).decode("utf-8")

        iv_b64, ct_b64 = ciphertext.split(":", 1)
        iv = base64.b64decode(iv_b64, validate=True)
        ct = base64.b64decode(ct_b64, validate=True)
        cipher = AES.new(self._legacy_aes_key, AES.MODE_CBC, iv=iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode("utf-8")

    def _mask_key(self, raw_key: str) -> str:
        """生成掩码展示：sk-...****xxxx"""
        if len(raw_key) <= 8:
            return "****"
        return raw_key[:3] + "..." + "****" + raw_key[-4:]

    async def save_key(self, user_id: int, provider: str, api_key: str) -> ApiKeyStatusResponse:
        """加密保存用户 API Key"""
        normalized_key = api_key.strip()
        if provider not in self._SUPPORTED_PROVIDERS:
            raise ValueError("不支持的 API Key 提供商")
        if len(normalized_key) < 10:
            raise ValueError("API Key 长度不足")
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")
        user.llm_provider = provider
        user.llm_api_key = self._encrypt(normalized_key)
        await self.db.flush()
        return ApiKeyStatusResponse(
            has_key=True,
            provider=provider,
            masked_key=self._mask_key(normalized_key),
        )

    async def require_decrypted_key(self, user_id: int) -> Tuple[str, str]:
        """Return a user's provider key or fail closed when BYOK is incomplete."""
        user_key = await self.get_decrypted_key(user_id)
        if user_key is None:
            raise ApiKeyRequiredError("使用 AI 功能前，请先配置你自己的 API Key")
        return user_key

    async def delete_key(self, user_id: int) -> ApiKeyStatusResponse:
        """清除用户 API Key，并停用该用户的 AI 生成功能。"""
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
        if (
            not user
            or user.llm_provider not in self._SUPPORTED_PROVIDERS
            or not user.llm_api_key
        ):
            return ApiKeyStatusResponse(has_key=False)
        try:
            raw_key = self._decrypt(user.llm_api_key).strip()
            if not raw_key:
                return ApiKeyStatusResponse(has_key=False)
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
        if (
            not user
            or user.llm_provider not in self._SUPPORTED_PROVIDERS
            or not user.llm_api_key
        ):
            return None
        try:
            raw_key = self._decrypt(user.llm_api_key).strip()
            if not raw_key:
                return None
            return user.llm_provider, raw_key
        except Exception:
            return None
