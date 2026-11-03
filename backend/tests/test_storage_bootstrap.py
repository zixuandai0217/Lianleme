"""开发环境的内存存储不应被当成「缺少 MinIO 依赖」。

回归背景：本地用 SQLite 启动时存储端口是内存实现，但启动仍然去连 MinIO
（约 30 秒重试）且 /health/ready 报 object_storage 失败，看起来像跑不起来。
"""
import asyncio

from app.core import health, storage
from app.core.config import settings


def _dev_sqlite(monkeypatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///./dev.db")


def test_uses_in_memory_storage_only_for_dev_sqlite(monkeypatch) -> None:
    _dev_sqlite(monkeypatch)
    assert storage.uses_in_memory_storage() is True

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    assert storage.uses_in_memory_storage() is False

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
    assert storage.uses_in_memory_storage() is False


def test_probe_object_storage_skips_minio_for_memory_storage(monkeypatch) -> None:
    _dev_sqlite(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("MinIO must not be probed when storage is in-memory")

    monkeypatch.setattr(storage, "bounded_minio_client", forbidden)
    asyncio.run(health.probe_object_storage())
