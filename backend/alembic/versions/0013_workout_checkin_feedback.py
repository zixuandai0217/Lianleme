"""workout_checkin_feedback：打卡记录引用调整作业与提交时刻状态（工单 28）

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-02

打卡现在负责投递一条可查询的调整作业，并在打卡记录上留下**引用**：

- ``adjustment_job_id``（String(32)）：读取反馈时按它投影作业与调整结论；
- ``plan_impact_status``（String(24)，可空）：提交时刻的状态快照，只用于在没有
  作业可读时说明「未投递」，不复制方向 / 理由等结论文本。

两列都刻意不加外键（与 ``training_plans.latest_adjustment_id`` 同一约定）：
作业表已经通过 user_id 指向用户，反向再加外键会让迁移顺序与 SQLite batch 模式
变复杂；引用完整性由写入路径保证。DDL 与 ``app/models/record.py`` 逐列对齐
（ORM 是唯一事实源），downgrade 只丢弃本 revision 追加的两列。
"""
import sqlalchemy as sa

from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workout_records',
        sa.Column('adjustment_job_id', sa.String(32), nullable=True),
    )
    op.add_column(
        'workout_records',
        sa.Column('plan_impact_status', sa.String(24), nullable=True),
    )
    # 先清掉历史重复（保留最新一条），再建「一天一条」唯一索引。
    op.execute(
        "DELETE FROM workout_records WHERE id NOT IN ("
        "SELECT MAX(id) FROM workout_records GROUP BY user_id, workout_date)"
    )
    op.create_index(
        'uq_workout_records_user_date',
        'workout_records',
        ['user_id', 'workout_date'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_workout_records_user_date', table_name='workout_records')
    op.drop_column('workout_records', 'plan_impact_status')
    op.drop_column('workout_records', 'adjustment_job_id')
