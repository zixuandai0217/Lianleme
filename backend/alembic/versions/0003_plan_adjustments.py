"""plan_adjustments：调整结论落盘（工单 08）

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02

DDL 与 ``app/models/adjustment.py`` 逐列对齐（ORM 是唯一事实源）。
``training_plans.latest_adjustment_id`` 只存引用、不建外键——反向外键会与
``plan_adjustments.plan_id`` 形成环，破坏建表顺序与 SQLite batch 迁移。
"""
import sqlalchemy as sa

from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'plan_adjustments',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'plan_id',
            sa.Integer,
            sa.ForeignKey('training_plans.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('direction', sa.String(16), nullable=False),
        sa.Column('reason', sa.String(255), nullable=False),
        sa.Column('completion_rate', sa.Float, nullable=False),
        sa.Column('difficulty_rating', sa.Float, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_plan_adjustments_user_id', 'plan_adjustments', ['user_id'])
    op.create_index('ix_plan_adjustments_plan_id', 'plan_adjustments', ['plan_id'])
    op.create_index(
        'ix_plan_adjustments_user_created_at',
        'plan_adjustments',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'ix_plan_adjustments_plan_created_at',
        'plan_adjustments',
        ['plan_id', 'created_at'],
    )
    op.add_column(
        'training_plans',
        sa.Column('latest_adjustment_id', sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('training_plans', 'latest_adjustment_id')
    op.drop_index('ix_plan_adjustments_plan_created_at', table_name='plan_adjustments')
    op.drop_index('ix_plan_adjustments_user_created_at', table_name='plan_adjustments')
    op.drop_index('ix_plan_adjustments_plan_id', table_name='plan_adjustments')
    op.drop_index('ix_plan_adjustments_user_id', table_name='plan_adjustments')
    op.drop_table('plan_adjustments')
