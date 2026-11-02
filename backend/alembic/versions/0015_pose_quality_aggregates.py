"""pose_quality_aggregates：跨会话姿态质量数值聚合（工单 43）

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-02

关键点序列只在会话内存中处理，结束后丢弃；这里只落一行数值摘要：
周期数、可评估/不可评估计数、平均质量分、问题类型直方图与模型调用次数。
DDL 与 ``app/models/pose_aggregate.py`` 逐列对齐（ORM 是唯一事实源），
``session_id`` 唯一保证重复结束不重复写行；downgrade 只丢弃本 revision 新建的表。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pose_quality_aggregates',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('session_id', sa.String(64), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cycles_count', sa.Integer, nullable=False),
        sa.Column('evaluable_cycles', sa.Integer, nullable=False),
        sa.Column('not_evaluable_cycles', sa.Integer, nullable=False),
        sa.Column('avg_quality', sa.Float, nullable=False),
        sa.Column('issues_histogram', JSONB, nullable=False),
        sa.Column('model_calls', sa.Integer, nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        'ix_pose_quality_aggregates_user_id', 'pose_quality_aggregates', ['user_id']
    )
    op.create_index(
        'ix_pose_quality_aggregates_session_id',
        'pose_quality_aggregates',
        ['session_id'],
        unique=True,
    )
    op.create_index(
        'ix_pose_quality_aggregates_finished_at',
        'pose_quality_aggregates',
        ['finished_at'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_pose_quality_aggregates_finished_at', table_name='pose_quality_aggregates'
    )
    op.drop_index(
        'ix_pose_quality_aggregates_session_id', table_name='pose_quality_aggregates'
    )
    op.drop_index(
        'ix_pose_quality_aggregates_user_id', table_name='pose_quality_aggregates'
    )
    op.drop_table('pose_quality_aggregates')
