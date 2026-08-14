"""环境变量配置：从 .env 文件读取所有运行时参数"""

from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_AES_SECRETS = {
    "default-32-byte-secret-key!!!!!!",
    "dev-32-byte-secret-key-here!!!!!",
    "your-32-byte-secret-key-here!!!!",
}


class Settings(BaseSettings):
    """Load runtime configuration and reject unsafe production encryption settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 应用
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    ALLOWED_ORIGINS: List[str] = []

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://lianleme:lianle123@localhost:5432/lianleme"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO / 对象存储
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minio123"
    MINIO_BUCKET: str = "lianleme-photos"

    # LLM 系统默认 Key
    # 允许未配置个人 Key 的登录用户回退到系统 Key（仅限中央付费部署按需开启，默认关闭）
    ALLOW_SYSTEM_LLM_FALLBACK: bool = False
    DEFAULT_LLM_PROVIDER: str = "qwen"
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_VISION_MODEL: str = "gpt-4o"
    QWEN_API_KEY: str = ""
    QWEN_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_CHAT_MODEL: str = "qwen3.5-flash-2026-02-23"
    QWEN_VISION_MODEL: str = "qwen3.5-flash-2026-02-23"

    # Qwen3-TTS 系统音色合成与原创音色设计
    QWEN_AUDIO_API_KEY: str = ""
    QWEN_AUDIO_API_BASE: str = "https://dashscope.aliyuncs.com/api/v1"
    QWEN_AUDIO_TTS_MODEL: str = "qwen3-tts-flash"
    QWEN_AUDIO_TTS_VOICE: str = "Ryan"
    QWEN_BYOK_TTS_VOICE: str = "Ryan"
    QWEN_AUDIO_VOICE_DESIGN_MODEL: str = "qwen3-tts-vd-2026-01-26"
    RHUBARB_BIN: str = ".tools/rhubarb/rhubarb"
    RHUBARB_TIMEOUT_SECONDS: float = 15.0

    # AES-256 用于加密用户 API Key（必须 32 字节）
    AES_SECRET_KEY: str = "default-32-byte-secret-key!!!!!!"

    @model_validator(mode="after")
    def validate_api_key_encryption_secret(self) -> "Settings":
        """Prevent non-development startup with a public, missing, or undersized AES secret."""
        if self.APP_ENV.strip().lower() == "development":
            return self

        secret = self.AES_SECRET_KEY.strip()
        if len(secret.encode("utf-8")) < 32 or secret in _INSECURE_AES_SECRETS:
            raise ValueError(
                "AES_SECRET_KEY must be a unique deployment secret of at least 32 bytes"
            )
        return self

    def system_llm_credentials(self) -> tuple[str, str] | None:
        """Return usable server-managed (provider, api_key) or None.

        Only DEFAULT_LLM_PROVIDER providers with a non-blank configured system key
        qualify. Non-secret helper: it never logs or persists the returned key.
        """
        provider = self.DEFAULT_LLM_PROVIDER.strip().lower()
        if provider == "qwen":
            api_key = self.QWEN_API_KEY.strip()
        elif provider == "openai":
            api_key = self.OPENAI_API_KEY.strip()
        else:
            return None
        if not api_key:
            return None
        return provider, api_key


settings = Settings()
