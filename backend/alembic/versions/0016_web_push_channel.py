"""web push channel：推送订阅与待执行推送作业（工单 35）

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-02

DDL 与 ``app/models/push.py`` 逐列对齐（ORM 是唯一事实源）：
- ``push_subscriptions``：endpoint 唯一，注销只把 ``is_active`` 置否；
- ``push_jobs``：``delivery_id`` 唯一，保证一条投递记录最多一条作业。

``upgrade`` 只新增本 revision 的两张表与索引，``downgrade`` 只丢弃它们。
"""
import sqlalchemy as sa

from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('endpoint', sa.Text, nullable=False),
        sa.Column('p256dh', sa.String(255), nullable=False),
        sa.Column('auth', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.String(64), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id'])
    op.create_index(
        'uq_push_subscriptions_endpoint', 'push_subscriptions', ['endpoint'], unique=True
    )

    op.create_table(
        'push_jobs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'delivery_id',
            sa.Integer,
            sa.ForeignKey('reminder_deliveries.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'subscription_id',
            sa.Integer,
            sa.ForeignKey('push_subscriptions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer, nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_push_jobs_user_id', 'push_jobs', ['user_id'])
    op.create_index('ix_push_jobs_subscription_id', 'push_jobs', ['subscription_id'])
    op.create_index('uq_push_jobs_delivery_id', 'push_jobs', ['delivery_id'], unique=True)
    op.create_index(
        'ix_push_jobs_status_created_at', 'push_jobs', ['status', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_push_jobs_status_created_at', table_name='push_jobs')
    op.drop_index('uq_push_jobs_delivery_id', table_name='push_jobs')
    op.drop_index('ix_push_jobs_subscription_id', table_name='push_jobs')
    op.drop_index('ix_push_jobs_user_id', table_name='push_jobs')
    op.drop_table('push_jobs')

    op.drop_index('uq_push_subscriptions_endpoint', table_name='push_subscriptions')
    op.drop_index('ix_push_subscriptions_user_id', table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
