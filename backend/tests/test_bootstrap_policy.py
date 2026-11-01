"""启动建表策略：只有开发环境的 SQLite 才允许用 ORM 元数据建表。

生产库只走迁移——否则「迁移与 ORM 必须逐列一致」这条约定会被启动时的
create_all 悄悄掩盖，迁移评审也就失去意义。
"""

import pytest

from app.core.config import settings
from app.main import uses_orm_bootstrap


@pytest.mark.parametrize(
    ("app_env", "database_url", "expected"),
    [
        ("development", "sqlite+aiosqlite:///./dev.db", True),
        ("development", "postgresql+asyncpg://user:pass@db/app", False),
        ("production", "sqlite+aiosqlite:///./dev.db", False),
        ("production", "postgresql+asyncpg://user:pass@db/app", False),
    ],
)
def test_bootstrap_policy(monkeypatch, app_env: str, database_url: str, expected: bool):
    monkeypatch.setattr(settings, "APP_ENV", app_env)
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)

    assert uses_orm_bootstrap() is expected
