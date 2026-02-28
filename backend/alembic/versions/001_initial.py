"""
初始迁移 - 创建所有表
Revision ID: initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 用户表
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('openid', sa.String(length=64), nullable=True),
        sa.Column('username', sa.String(length=50), nullable=True),
        sa.Column('nickname', sa.String(length=50), nullable=True),
        sa.Column('avatar_url', sa.String(length=500), nullable=True),
        sa.Column('gender', sa.Integer(), nullable=True, comment='性别：0-未知 1-男 2-女'),
        sa.Column('birthday', sa.Date(), nullable=True, comment='生日'),
        sa.Column('phone', sa.String(length=20), nullable=True, comment='手机号'),
        sa.Column('current_profile_id', sa.Integer(), nullable=True, comment='当前生效身体数据 ID'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_openid'), 'users', ['openid'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # 身体数据表
    op.create_table('profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False, comment='身高 cm'),
        sa.Column('weight', sa.Float(), nullable=False, comment='体重 kg'),
        sa.Column('body_fat_rate', sa.Float(), nullable=True, comment='体脂率 %'),
        sa.Column('muscle_mass', sa.Float(), nullable=True, comment='肌肉量 kg'),
        sa.Column('bmi', sa.Float(), nullable=True, comment='BMI 指数'),
        sa.Column('target_weight', sa.Float(), nullable=True, comment='目标体重 kg'),
        sa.Column('target_body_fat', sa.Float(), nullable=True, comment='目标体脂率 %'),
        sa.Column('weekly_goal', sa.Float(), nullable=True, comment='每周目标减重 kg'),
        sa.Column('goal_type', sa.String(length=20), nullable=True, comment='目标类型'),
        sa.Column('activity_level', sa.String(length=20), nullable=True, comment='活动水平'),
        sa.Column('exercise_days_per_week', sa.Integer(), nullable=True, comment='每周运动天数'),
        sa.Column('health_issues', sa.JSON(), nullable=True, comment='健康问题'),
        sa.Column('allergies', sa.JSON(), nullable=True, comment='食物过敏'),
        sa.Column('preferences', sa.JSON(), nullable=True, comment='饮食偏好'),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profiles_id'), 'profiles', ['id'], unique=False)
    op.create_index(op.f('ix_profiles_user_id'), 'profiles', ['user_id'], unique=False)

    # 饮食计划表
    op.create_table('diet_plans',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('daily_calories', sa.Integer(), nullable=False, comment='每日热量 kcal'),
        sa.Column('protein', sa.Float(), nullable=False, comment='蛋白质 g'),
        sa.Column('carbohydrates', sa.Float(), nullable=False, comment='碳水 g'),
        sa.Column('fat', sa.Float(), nullable=False, comment='脂肪 g'),
        sa.Column('water', sa.Integer(), nullable=True, comment='饮水 ml'),
        sa.Column('meals', sa.JSON(), nullable=False, comment='餐次分配'),
        sa.Column('preferences', sa.JSON(), nullable=True),
        sa.Column('avoid_foods', sa.JSON(), nullable=True),
        sa.Column('plan_date', sa.Date(), nullable=False, comment='计划日期'),
        sa.Column('generated_by', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_diet_plans_id'), 'diet_plans', ['id'], unique=False)
    op.create_index(op.f('ix_diet_plans_plan_date'), 'diet_plans', ['plan_date'], unique=False)
    op.create_index(op.f('ix_diet_plans_user_id'), 'diet_plans', ['user_id'], unique=False)

    # 运动计划表
    op.create_table('workout_plans',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('weekly_workout_days', sa.Integer(), nullable=True),
        sa.Column('estimated_calories_burn', sa.Integer(), nullable=True),
        sa.Column('week_plan', sa.JSON(), nullable=False),
        sa.Column('plan_start_date', sa.Date(), nullable=False),
        sa.Column('plan_end_date', sa.Date(), nullable=False),
        sa.Column('generated_by', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workout_plans_id'), 'workout_plans', ['id'], unique=False)
    op.create_index(op.f('ix_workout_plans_user_id'), 'workout_plans', ['user_id'], unique=False)

    # 饮食记录表
    op.create_table('diet_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('log_date', sa.Date(), nullable=False, comment='记录日期'),
        sa.Column('meal_type', sa.String(length=20), nullable=False, comment='餐类型'),
        sa.Column('foods', sa.JSON(), nullable=False, comment='食物列表'),
        sa.Column('total_calories', sa.Integer(), nullable=True),
        sa.Column('total_protein', sa.Float(), nullable=True),
        sa.Column('total_carbs', sa.Float(), nullable=True),
        sa.Column('total_fat', sa.Float(), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['diet_plans.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_diet_logs_id'), 'diet_logs', ['id'], unique=False)
    op.create_index(op.f('ix_diet_logs_log_date'), 'diet_logs', ['log_date'], unique=False)
    op.create_index(op.f('ix_diet_logs_user_id'), 'diet_logs', ['user_id'], unique=False)

    # 运动记录表
    op.create_table('workout_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('workout_date', sa.Date(), nullable=False, comment='训练日期'),
        sa.Column('day_number', sa.Integer(), nullable=True),
        sa.Column('workout_type', sa.String(length=50), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column('calories_burned', sa.Integer(), nullable=True),
        sa.Column('exercises_completed', sa.JSON(), nullable=True),
        sa.Column('heart_rate_avg', sa.Integer(), nullable=True),
        sa.Column('heart_rate_max', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['workout_plans.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workout_logs_id'), 'workout_logs', ['id'], unique=False)
    op.create_index(op.f('ix_workout_logs_user_id'), 'workout_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_workout_logs_workout_date'), 'workout_logs', ['workout_date'], unique=False)

    # 每日统计表
    op.create_table('daily_stats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('stat_date', sa.Date(), nullable=False, comment='统计日期'),
        sa.Column('calories_in', sa.Integer(), nullable=True),
        sa.Column('protein_in', sa.Float(), nullable=True),
        sa.Column('carbs_in', sa.Float(), nullable=True),
        sa.Column('fat_in', sa.Float(), nullable=True),
        sa.Column('water_ml', sa.Integer(), nullable=True),
        sa.Column('calories_out', sa.Integer(), nullable=True),
        sa.Column('exercise_calories', sa.Integer(), nullable=True),
        sa.Column('steps', sa.Integer(), nullable=True),
        sa.Column('net_calories', sa.Integer(), nullable=True),
        sa.Column('diet_plan_completed', sa.Boolean(), nullable=True),
        sa.Column('workout_completed', sa.Boolean(), nullable=True),
        sa.Column('weight', sa.Float(), nullable=True),
        sa.Column('body_fat_rate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'stat_date', name='user_date_unique')
    )
    op.create_index(op.f('ix_daily_stats_id'), 'daily_stats', ['id'], unique=False)
    op.create_index(op.f('ix_daily_stats_stat_date'), 'daily_stats', ['stat_date'], unique=False)
    op.create_index(op.f('ix_daily_stats_user_id'), 'daily_stats', ['user_id'], unique=False)

    # 聊天消息表
    op.create_table('chat_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False, comment='会话 ID'),
        sa.Column('role', sa.String(length=20), nullable=False, comment='角色'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_user_id'), 'chat_messages', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('chat_messages')
    op.drop_table('daily_stats')
    op.drop_table('workout_logs')
    op.drop_table('diet_logs')
    op.drop_table('workout_plans')
    op.drop_table('diet_plans')
    op.drop_table('profiles')
    op.drop_table('users')
