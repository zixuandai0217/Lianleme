"""analysis task persistence

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01

Adds the durable analysis task table.  Task execution facts live here while the
existing body_analysis_records table remains the long-lived history asset; the
optional ``history_record_id`` links a completed task to its history row.

The DDL below is kept column-for-column aligned with
``app/models/analysis_task.py`` (ORM remains the single source of truth).  JSON
columns use the shared compatibility type so SQLite and Postgres receive the
same logical schema without business-layer dialect branches.
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'analysis_tasks',
        sa.Column('task_id', sa.String(64), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('stage', sa.String(16), nullable=False),
        sa.Column('attempt', sa.Integer, nullable=False),
        sa.Column('progress', sa.Integer, nullable=False),
        sa.Column('result', JSONB, nullable=True),
        sa.Column('error_code', sa.String(64), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_retryable', sa.Boolean, nullable=True),
        sa.Column('request_id', sa.String(64), nullable=True),
        sa.Column('input_image_base64', sa.Text, nullable=True),
        sa.Column('input_profile', JSONB, nullable=True),
        sa.Column(
            'history_record_id',
            sa.Integer,
            sa.ForeignKey('body_analysis_records.id', ondelete='SET NULL'),
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
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lease_owner', sa.String(64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_analysis_tasks_user_id', 'analysis_tasks', ['user_id'])
    op.create_index('ix_analysis_tasks_status', 'analysis_tasks', ['status'])


def downgrade() -> None:
    op.drop_index('ix_analysis_tasks_status', table_name='analysis_tasks')
    op.drop_index('ix_analysis_tasks_user_id', table_name='analysis_tasks')
    op.drop_table('analysis_tasks')
