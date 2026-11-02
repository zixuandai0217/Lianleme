"""plan_adjustments 追加五维明细与合并小结（工单 24）

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-02

在工单 08 的调整结论记录上**追加**四列，不新建并行存储：一次调整仍只有一条记录，
工单 26 的详情直接读这里。全部可空——旧记录没有评估明细，读取按「无明细」降级。
DDL 与 ``app/models/adjustment.py`` 逐列对齐（ORM 是唯一事实源），downgrade 只丢弃
本 revision 追加的列。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('plan_adjustments', sa.Column('overall_score', sa.Float, nullable=True))
    op.add_column('plan_adjustments', sa.Column('delta_percent', sa.Float, nullable=True))
    op.add_column('plan_adjustments', sa.Column('dimensions', JSONB, nullable=True))
    op.add_column('plan_adjustments', sa.Column('merged', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('plan_adjustments', 'merged')
    op.drop_column('plan_adjustments', 'dimensions')
    op.drop_column('plan_adjustments', 'delta_percent')
    op.drop_column('plan_adjustments', 'overall_score')
