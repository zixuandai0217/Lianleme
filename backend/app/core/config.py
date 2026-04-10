"""环境变量配置：从 .env 文件读取所有运行时参数"""
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    # 微信
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    # LLM 系统默认 Key
    DEFAULT_LLM_PROVIDER: str = "qwen"
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_VISION_MODEL: str = "gpt-4o"
    QWEN_API_KEY: str = ""
    QWEN_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_CHAT_MODEL: str = "qwen3.5-flash-2026-02-23"
    QWEN_VISION_MODEL: str = "qwen3.5-flash-2026-02-23"

    # AES-256 用于加密用户 API Key（必须 32 字节）
    AES_SECRET_KEY: str = "default-32-byte-secret-key!!!!!!"


settings = Settings()
