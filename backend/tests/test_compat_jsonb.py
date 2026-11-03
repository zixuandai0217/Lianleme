"""compat.JSONB 必须按方言选择实现，而不是按进程启动时的 DATABASE_URL。

回归背景：CI 没有 backend/.env（settings 默认 PostgreSQL），测试却用 SQLite
建表；旧实现导入时就锁定成 PostgreSQL JSONB，导致
``SQLiteTypeCompiler can't render element of type JSONB``。
"""
import pytest
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB

from app.core.compat import JSONB


def test_jsonb_uses_native_type_on_postgres() -> None:
    assert isinstance(JSONB().load_dialect_impl(postgresql.dialect()), PGJSONB)


def test_jsonb_falls_back_to_text_on_sqlite() -> None:
    assert isinstance(JSONB().load_dialect_impl(sqlite.dialect()), Text)


def test_jsonb_compiles_on_sqlite_regardless_of_settings() -> None:
    """旧实现只有在 settings 指向 SQLite 时才走 Text；这里直接编译 SQLite DDL。"""
    assert JSONB().compile(dialect=sqlite.dialect()).upper() == "TEXT"


@pytest.mark.parametrize("value", [None, {"a": 1}, [1, 2, 3], "text"])
def test_jsonb_sqlite_roundtrip(value) -> None:
    dialect = sqlite.dialect()
    bound = JSONB().process_bind_param(value, dialect)
    assert JSONB().process_result_value(bound, dialect) == value
