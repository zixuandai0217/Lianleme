"""Alembic 迁移配置"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 导入模型
from app.database import Base
from app.models import User, Profile, DietPlan, WorkoutPlan, DietLog, WorkoutLog, DailyStat, ChatMessage

# Alembic Config
config = context.config

# 设置数据库 URL
from app.config import settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 导入 model 用于 autogenerate
target_metadata = Base.metadata

# 其他配置
def run_migrations_offline() -> None:
    """离线模式运行迁移"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式运行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
