"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-08

基线迁移，与 app/models 下的 ORM 定义逐列对齐（ORM 是唯一事实源）：
users / training_plans / workout_records / weight_records /
body_analysis_records / chat_messages。

落地约定（见 .scratch/analysis-task-persistence/issue.md 第 7 节）：
- 主键统一为自增整数，外键类型与 users.id 完全一致，不再有 UUID / gen_random_uuid() 假设；
- JSON 列使用兼容层 app.core.compat.JSONB，数据库方言差异只出现在兼容层；
- downgrade() 删除本迁移创建的全部对象，可回滚到 base。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def _timestamp_columns() -> list[sa.Column]:
    """created_at / updated_at：与模型一致，带数据库侧默认时间。"""
    return [
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
    ]


def upgrade() -> None:
    # users 表
    op.create_table(
        'users',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('openid', sa.String(64), nullable=False),
        sa.Column('email', sa.String(128), nullable=True),
        sa.Column('password_hash', sa.String(128), nullable=True),
        sa.Column('nickname', sa.String(64), nullable=True),
        sa.Column('avatar_url', sa.Text, nullable=True),
        sa.Column('profile', JSONB, nullable=True),          # 身高/体重/目标/训练经验等
        sa.Column('body_analysis', JSONB, nullable=True),    # 最近一次体型分析结果
        sa.Column('is_admin', sa.Boolean, nullable=False, server_default='0'),
        sa.Column('llm_provider', sa.String(16), nullable=True),
        sa.Column('llm_api_key', sa.Text, nullable=True),    # AES-256 加密存储
        *_timestamp_columns(),
    )
    op.create_index('ix_users_openid', 'users', ['openid'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # training_plans 表
    op.create_table(
        'training_plans',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('week_start', sa.Date, nullable=False),
        sa.Column('weekly_plan', JSONB, nullable=False),               # 七天训练计划 JSON
        sa.Column('body_analysis_snapshot', JSONB, nullable=True),     # 生成依据的体型快照
        sa.Column('difficulty_factor', sa.Float, nullable=False),      # 整体难度系数
        sa.Column('status', sa.String(16), nullable=False),            # active / archived
        *_timestamp_columns(),
    )
    op.create_index('ix_training_plans_user_id', 'training_plans', ['user_id'])

    # workout_records 表
    op.create_table(
        'workout_records',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
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
        sa.Column('workout_date', sa.Date, nullable=False),
        sa.Column('total_sets', sa.Integer, nullable=False),        # 计划总组数
        sa.Column('completed_sets', sa.Integer, nullable=False),    # 实际完成组数
        sa.Column('completion_rate', sa.Float, nullable=False),     # 0.0-1.0
        sa.Column('duration_minutes', sa.Integer, nullable=False),  # 训练时长（分钟）
        sa.Column('difficulty_rating', sa.Integer, nullable=True),  # 1-5 用户自评
        sa.Column('detail', JSONB, nullable=True),                  # 各动作完成情况
        sa.Column('ai_feedback', sa.Text, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_workout_records_user_id', 'workout_records', ['user_id'])
    op.create_index('ix_workout_records_workout_date', 'workout_records', ['workout_date'])

    # weight_records 表
    op.create_table(
        'weight_records',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('weight', sa.Float, nullable=False),           # 体重 kg
        sa.Column('recorded_date', sa.Date, nullable=False),     # 记录日期
        sa.Column('note', sa.Text, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_weight_records_user_id', 'weight_records', ['user_id'])
    op.create_index('ix_weight_records_recorded_date', 'weight_records', ['recorded_date'])

    # body_analysis_records 表
    op.create_table(
        'body_analysis_records',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('image_thumbnail', sa.Text, nullable=True),  # 缩略图 base64
        sa.Column('result', JSONB, nullable=False),            # BodyAnalysisResult 完整 JSON
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_body_analysis_records_user_id', 'body_analysis_records', ['user_id'])

    # chat_messages 表
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('role', sa.String(16), nullable=False),  # user / assistant
        sa.Column('content', sa.Text, nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_chat_messages_user_id', 'chat_messages', ['user_id'])


def downgrade() -> None:
    op.drop_table('chat_messages')
    op.drop_table('body_analysis_records')
    op.drop_table('weight_records')
    op.drop_table('workout_records')
    op.drop_table('training_plans')
    op.drop_table('users')
