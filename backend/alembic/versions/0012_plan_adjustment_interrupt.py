"""plan_adjustment_interrupt：HITL 待选择字段（工单 27）

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-02

命中风险条件的调整会挂成 ``pending_choice``，等待用户在三选一里拍板；因此作业行
需要记住「谁做的决定」「选了哪一档」「待选择窗口何时到期」。三列都可空：

- ``chosen_by``（String(16)）：``user`` / ``timeout_default``；未落地为空；
- ``chosen_option``（String(32)）：落地方案的稳定 id；未落地为空；
- ``interrupt_expires_at``（带时区 DateTime）：读取路径据此做惰性超时收敛，
  进程重启后延迟任务丢失也不会让作业卡在待确认。

DDL 与 ``app/models/adjustment_job.py`` 逐列对齐（ORM 是唯一事实源），
downgrade 只丢弃本 revision 追加的三列。
"""
import sqlalchemy as sa

from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'plan_adjustment_jobs',
        sa.Column('chosen_by', sa.String(16), nullable=True),
    )
    op.add_column(
        'plan_adjustment_jobs',
        sa.Column('chosen_option', sa.String(32), nullable=True),
    )
    op.add_column(
        'plan_adjustment_jobs',
        sa.Column('interrupt_expires_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('plan_adjustment_jobs', 'interrupt_expires_at')
    op.drop_column('plan_adjustment_jobs', 'chosen_option')
    op.drop_column('plan_adjustment_jobs', 'chosen_by')
