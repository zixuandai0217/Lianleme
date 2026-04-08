"""
LLMClientFactory：统一 LLM 客户端工厂
优先使用用户自有 API Key，未配置时降级到系统 .env 默认 Key
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
        - 优先级：用户自有 Key > 系统默认 Key
        """
        provider, api_key = await self._resolve_key(user_id)
        return self._build_client(provider, api_key, model_type, streaming)

    async def _resolve_key(self, user_id: Optional[int]) -> tuple[str, str]:
        """解析最终使用的 provider 和 api_key"""
        if user_id and self.db:
            key_service = ApiKeyService(self.db)
            user_key = await key_service.get_decrypted_key(user_id)
            if user_key:
                provider, raw_key = user_key
                return provider, raw_key

        # 降级到系统默认
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
            model_name = "qwen-vl-plus" if model_type == "vision" else "qwen-turbo"
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=settings.QWEN_API_BASE,
                streaming=streaming,
                timeout=30,
                max_retries=2,
            )
        else:
            model_name = "gpt-4o" if model_type == "vision" else "gpt-4o"
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                streaming=streaming,
                timeout=30,
                max_retries=2,
            )
