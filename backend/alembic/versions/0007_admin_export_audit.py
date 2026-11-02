"""admin_export_audits：导出审计（工单 38）

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02

DDL 与 ``app/models/admin_export_audit.py`` 逐列对齐。审计表只追加：成功与被拒绝
的导出各留一条，``rejection_reason`` 只在被拒时有值（成功为 NULL）。
"""
import sqlalchemy as sa

from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'admin_export_audits',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'operator_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('filter_summary', sa.String(512), nullable=False),
        sa.Column('filter_hash', sa.String(16), nullable=False),
        sa.Column('row_count', sa.Integer, nullable=False),
        sa.Column('outcome', sa.String(16), nullable=False),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        'ix_admin_export_audits_operator_id', 'admin_export_audits', ['operator_id']
    )
    op.create_index(
        'ix_admin_export_audits_created_at', 'admin_export_audits', ['created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_admin_export_audits_created_at', table_name='admin_export_audits')
    op.drop_index('ix_admin_export_audits_operator_id', table_name='admin_export_audits')
    op.drop_table('admin_export_audits')
