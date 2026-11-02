"""plan_explanation：计划解释字段落库（工单 20）

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02

DDL 与 ``app/models/plan.py`` 逐列对齐（ORM 是唯一事实源）：本次只给
``training_plans`` 追加两列可空列，不回填历史数据。

- ``profile_snapshot``（JSONB）：生成时的档案快照。只有存下当时的目标，读取解释时
  才不会拿用户后来改过的档案做错误归因；旧计划为空 → 「按当前档案推断」降级。
- ``analysis_captured_at``（带时区 DateTime）：该次体型分析快照被本计划捕获的时间。
  分析结果本身不带时间戳，因此记捕获时刻作为可核对定位；旧计划为空 → 「分析时间未知」。

downgrade() 精确删除 upgrade() 追加的这两列，可回滚到 0005。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'training_plans',
        sa.Column('profile_snapshot', JSONB, nullable=True),
    )
    op.add_column(
        'training_plans',
        sa.Column('analysis_captured_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('training_plans', 'analysis_captured_at')
    op.drop_column('training_plans', 'profile_snapshot')
