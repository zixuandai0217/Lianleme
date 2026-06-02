"""跨数据库兼容层：JSONB 在 SQLite 上回退为 JSON Text"""
import json

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    class JSONB(TypeDecorator):
        """SQLite 兼容 JSONB：序列化为 TEXT 列"""
        impl = Text
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is not None:
                return json.dumps(value, ensure_ascii=False)
            return None

        def process_result_value(self, value, dialect):
            if value is not None:
                return json.loads(value)
            return None
else:
    from sqlalchemy.dialects.postgresql import JSONB as JSONB  # noqa: F811
