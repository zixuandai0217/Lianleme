"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-04-08

创建初始数据库表：users / training_plans / workout_records
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users 表
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('openid', sa.String(64), nullable=False, unique=True),
        sa.Column('nickname', sa.String(64), nullable=True),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('height', sa.Float, nullable=True),
        sa.Column('weight', sa.Float, nullable=True),
        sa.Column('goal', sa.String(32), nullable=True),
        sa.Column('experience', sa.String(32), nullable=True),
        sa.Column('body_analysis', JSONB, nullable=True),
        sa.Column('llm_provider', sa.String(32), nullable=True, server_default='openai'),
        sa.Column('llm_api_key', sa.Text, nullable=True),  # AES-256 加密存储
        sa.Column('wx_subscribe', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_users_openid', 'users', ['openid'])

    # training_plans 表
    op.create_table(
        'training_plans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('week_start', sa.Date, nullable=False),
        sa.Column('days', JSONB, nullable=False),   # 7天训练计划数组
        sa.Column('intensity', sa.Integer, server_default='50'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_training_plans_user_id', 'training_plans', ['user_id'])

    # workout_records 表
    op.create_table(
        'workout_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id', UUID(as_uuid=True), sa.ForeignKey('training_plans.id', ondelete='SET NULL'), nullable=True),
        sa.Column('workout_date', sa.Date, nullable=False),
        sa.Column('duration_minutes', sa.Integer, nullable=True),
        sa.Column('completion_rate', sa.Float, nullable=True),  # 0.0-1.0
        sa.Column('difficulty_rating', sa.Integer, nullable=True),  # 1-5 用户自评
        sa.Column('exercises_done', JSONB, nullable=True),
        sa.Column('ai_feedback', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_workout_records_user_id', 'workout_records', ['user_id'])
    op.create_index('ix_workout_records_date', 'workout_records', ['workout_date'])


def downgrade() -> None:
    op.drop_table('workout_records')
    op.drop_table('training_plans')
    op.drop_table('users')
