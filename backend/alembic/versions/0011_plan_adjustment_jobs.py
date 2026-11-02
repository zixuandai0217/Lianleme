"""plan_adjustment_jobs：可查询的调整作业（工单 26）

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-02

打卡触发的调整从「后台动作」变成一张可查询的作业：稳定标识、状态、五维小结
引用、决策、计划前后差异与失败分类都在这里。状态词表包含 ``pending_choice`` /
``expired_no_choice``，但工单 26 只写入 ``evaluating`` / ``applied`` / ``failed``；
另外两个状态由工单 27 的 interrupt 流程产生。

DDL 与 ``app/models/adjustment_job.py`` 逐列对齐（ORM 是唯一事实源），
downgrade 只丢弃本 revision 新增的对象。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'plan_adjustment_jobs',
        sa.Column('job_id', sa.String(32), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column(
            'adjustment_id',
            sa.String(32),
            sa.ForeignKey('plan_adjustments.id', ondelete='SET NULL'),
            nullable=True,
        ),
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
        sa.Column('landed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.String(64), nullable=True),
        sa.Column('failure_class', sa.String(32), nullable=True),
        sa.Column('plan_diff', JSONB, nullable=True),
        sa.Column('decision', JSONB, nullable=True),
        sa.Column('interrupt', JSONB, nullable=True),
    )
    op.create_index('ix_plan_adjustment_jobs_user_id', 'plan_adjustment_jobs', ['user_id'])
    op.create_index(
        'ux_plan_adjustment_jobs_adjustment_id',
        'plan_adjustment_jobs',
        ['adjustment_id'],
        unique=True,
    )
    op.create_index(
        'ix_plan_adjustment_jobs_user_created_at',
        'plan_adjustment_jobs',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'ix_plan_adjustment_jobs_status_created_at',
        'plan_adjustment_jobs',
        ['status', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_plan_adjustment_jobs_status_created_at',
        table_name='plan_adjustment_jobs',
    )
    op.drop_index(
        'ix_plan_adjustment_jobs_user_created_at',
        table_name='plan_adjustment_jobs',
    )
    op.drop_index(
        'ux_plan_adjustment_jobs_adjustment_id',
        table_name='plan_adjustment_jobs',
    )
    op.drop_index('ix_plan_adjustment_jobs_user_id', table_name='plan_adjustment_jobs')
    op.drop_table('plan_adjustment_jobs')
