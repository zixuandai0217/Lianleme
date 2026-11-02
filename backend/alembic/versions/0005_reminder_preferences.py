"""reminder_preferences：提醒偏好（工单 34）

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02

DDL 与 ``app/models/reminder_preference.py`` 逐列对齐；一对一关系用 user_id 作主键，
免打扰区间存 ``HH:MM`` 文本，跨零点语义由判定函数负责，不落在数据库层。
"""
import sqlalchemy as sa

from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'reminder_preferences',
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column('daily_training_enabled', sa.Boolean, nullable=False),
        sa.Column('rest_day_note_enabled', sa.Boolean, nullable=False),
        sa.Column('recall_inactive_enabled', sa.Boolean, nullable=False),
        sa.Column('weekly_goal_enabled', sa.Boolean, nullable=False),
        sa.Column('onboarding_nudge_enabled', sa.Boolean, nullable=False),
        sa.Column('quiet_hours_start', sa.String(5), nullable=False),
        sa.Column('quiet_hours_end', sa.String(5), nullable=False),
        sa.Column('daily_cap', sa.Integer, nullable=False),
        sa.Column('weekly_goal_target', sa.Integer, nullable=False),
        sa.Column('timezone', sa.String(64), nullable=False),
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


def downgrade() -> None:
    op.drop_table('reminder_preferences')
