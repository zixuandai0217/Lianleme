"""跨数据库兼容层：JSONB 在 PostgreSQL 用原生 JSONB，其他方言回退为 JSON Text。

方言选择发生在绑定/编译阶段（``load_dialect_impl``），而不是导入阶段读
``settings.DATABASE_URL``。否则「本机 .env 是 SQLite、CI 没有 .env 走默认
PostgreSQL」会让同一个 SQLite 测试在两个环境里表现不同：CI 里 SQLite
编译器无法渲染 PostgreSQL 的 JSONB，直接建表失败。
"""
import json

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB
from sqlalchemy.types import TypeDecorator


class JSONB(TypeDecorator):
    """方言感知的 JSON 列：PostgreSQL 原生 JSONB，其余方言序列化为 TEXT。"""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGJSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        return None

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is not None:
            return json.loads(value)
        return None
