"""
LLMClientFactory：统一 LLM 客户端工厂
登录用户必须使用自有 API Key；无用户身份的内部任务可使用系统 Key
支持 OpenAI / 通义千问（兼容 OpenAI 接口格式）切换
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.services.user.api_key_service import ApiKeyService


class LLMClientFactory:
    """根据 user_id 解密并返回对应 LLM 客户端实例"""

    def __init__(self, db=None):
        self.db = db

    async def get_client(
        self,
        user_id: Optional[int] = None,
        model_type: str = "chat",
        streaming: bool = False,
    ) -> ChatOpenAI:
        """
        获取 LLM 客户端：
        - model_type: 'chat'（文本对话）或 'vision'（多模态）
        - 用户请求：必须使用用户自有 Key
        - 内部任务：user_id 为空时允许使用系统 Key
        """
        provider, api_key = await self._resolve_key(user_id)
        return self._build_client(provider, api_key, model_type, streaming)

    async def _resolve_key(self, user_id: Optional[int]) -> tuple[str, str]:
        """解析最终使用的 provider 和 api_key"""
        if user_id is not None:
            if self.db is None:
                raise ValueError("用户 AI 请求缺少数据库会话，无法读取 API Key")
            key_service = ApiKeyService(self.db)
            return await key_service.require_decrypted_key(user_id)

        # Internal jobs without a user identity may use server-managed credentials.
        return settings.DEFAULT_LLM_PROVIDER, (
            settings.QWEN_API_KEY
            if settings.DEFAULT_LLM_PROVIDER == "qwen"
            else settings.OPENAI_API_KEY
        )

    def _build_client(
        self, provider: str, api_key: str, model_type: str, streaming: bool
    ) -> ChatOpenAI:
        """根据 provider 构造 ChatOpenAI 实例（通义千问兼容 OpenAI 格式）"""
        if provider == "qwen":
            model_name = (
                settings.QWEN_VISION_MODEL if model_type == "vision" else settings.QWEN_CHAT_MODEL
            )
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=settings.QWEN_API_BASE,
                streaming=streaming,
                timeout=120,
                max_retries=2,
            )
        if provider == "openai":
            model_name = (
                settings.OPENAI_VISION_MODEL
                if model_type == "vision"
                else settings.OPENAI_CHAT_MODEL
            )
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                streaming=streaming,
                timeout=120,
                max_retries=2,
            )
        raise ValueError("不支持的 LLM 提供商")
