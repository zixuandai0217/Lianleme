"""reminder_deliveries：提醒投递记录 / 站内收件箱（工单 33）

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02

DDL 与 ``app/models/reminder.py`` 逐列对齐。唯一键（user_id, rule_code, local_date,
channel）是幂等契约的物理保证：重复 tick、进程重启与手动重跑都只能命中同一条记录。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'reminder_deliveries',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('rule_code', sa.String(32), nullable=False),
        sa.Column('local_date', sa.Date, nullable=False),
        sa.Column('channel', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('payload', JSONB, nullable=True),
        sa.Column('error_summary', sa.Text, nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            'user_id',
            'rule_code',
            'local_date',
            'channel',
            name='uq_reminder_deliveries_identity',
        ),
    )
    op.create_index('ix_reminder_deliveries_user_id', 'reminder_deliveries', ['user_id'])
    op.create_index(
        'ix_reminder_deliveries_user_created_at',
        'reminder_deliveries',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'ix_reminder_deliveries_user_read_at',
        'reminder_deliveries',
        ['user_id', 'read_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_reminder_deliveries_user_read_at', table_name='reminder_deliveries')
    op.drop_index('ix_reminder_deliveries_user_created_at', table_name='reminder_deliveries')
    op.drop_index('ix_reminder_deliveries_user_id', table_name='reminder_deliveries')
    op.drop_table('reminder_deliveries')
