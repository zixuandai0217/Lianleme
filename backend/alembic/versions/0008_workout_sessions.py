"""workout_sessions：训练会话聚合（工单 22）

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-02

DDL 与 ``app/models/workout_session.py`` 逐列对齐。同一用户同一本地日期最多一条会话
（唯一键），动作明细存 JSONB（随会话整体读写，不做行级更新）。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'workout_sessions',
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
        sa.Column('session_date', sa.Date, nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('total_sets', sa.Integer, nullable=False),
        sa.Column('completed_sets', sa.Integer, nullable=False),
        sa.Column('exercises', JSONB, nullable=True),
        sa.Column(
            'started_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            'last_activity_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('user_id', 'session_date', name='uq_workout_sessions_user_date'),
    )
    op.create_index('ix_workout_sessions_user_id', 'workout_sessions', ['user_id'])
    op.create_index('ix_workout_sessions_session_date', 'workout_sessions', ['session_date'])
    op.create_index(
        'ix_workout_sessions_user_status', 'workout_sessions', ['user_id', 'status']
    )
    op.create_index(
        'ix_workout_sessions_user_date', 'workout_sessions', ['user_id', 'session_date']
    )


def downgrade() -> None:
    op.drop_index('ix_workout_sessions_user_date', table_name='workout_sessions')
    op.drop_index('ix_workout_sessions_user_status', table_name='workout_sessions')
    op.drop_index('ix_workout_sessions_session_date', table_name='workout_sessions')
    op.drop_index('ix_workout_sessions_user_id', table_name='workout_sessions')
    op.drop_table('workout_sessions')
