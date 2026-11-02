"""媒体资产：对象 key 与元数据、分析记录资产引用（工单 14）

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-02

新增 ``media_assets`` 表：只保存对象 key 与元数据，不保存图片内容、不保存任何 URL。
同时给 ``analysis_tasks`` 与 ``body_analysis_records`` 追加原图/缩略图资产引用列；
引用是普通索引字符串而不是外键，便于后续工单清理资产时不产生级联耦合。

DDL 与 ``app/models/media_asset.py``、``analysis_task.py``、``body_analysis.py``
逐列对齐（ORM 是唯一事实源）。downgrade 只丢弃本 revision 新增的对象。
"""
import sqlalchemy as sa

from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'media_assets',
        sa.Column('asset_id', sa.String(64), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('object_key', sa.String(512), nullable=False, unique=True),
        sa.Column('content_type', sa.String(64), nullable=False),
        sa.Column('size_bytes', sa.Integer, nullable=False),
        sa.Column('width', sa.Integer, nullable=True),
        sa.Column('height', sa.Integer, nullable=True),
        sa.Column('checksum', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_media_assets_user_id', 'media_assets', ['user_id'])
    op.create_index('ix_media_assets_status', 'media_assets', ['status'])
    # 并发去重的唯一槽位：只在可用原图上唯一，删除后即可重新上传。
    op.create_index(
        'ux_media_assets_user_checksum',
        'media_assets',
        ['user_id', 'checksum'],
        unique=True,
        postgresql_where=sa.text("kind = 'original' AND status = 'available'"),
        sqlite_where=sa.text("kind = 'original' AND status = 'available'"),
    )

    op.add_column(
        'analysis_tasks',
        sa.Column('image_asset_id', sa.String(64), nullable=True),
    )
    op.add_column(
        'analysis_tasks',
        sa.Column('thumbnail_asset_id', sa.String(64), nullable=True),
    )
    op.create_index(
        'ix_analysis_tasks_image_asset_id', 'analysis_tasks', ['image_asset_id']
    )
    op.create_index(
        'ix_analysis_tasks_thumbnail_asset_id', 'analysis_tasks', ['thumbnail_asset_id']
    )

    op.add_column(
        'body_analysis_records',
        sa.Column('image_asset_id', sa.String(64), nullable=True),
    )
    op.add_column(
        'body_analysis_records',
        sa.Column('thumbnail_asset_id', sa.String(64), nullable=True),
    )
    op.create_index(
        'ix_body_analysis_records_image_asset_id',
        'body_analysis_records',
        ['image_asset_id'],
    )
    op.create_index(
        'ix_body_analysis_records_thumbnail_asset_id',
        'body_analysis_records',
        ['thumbnail_asset_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_body_analysis_records_thumbnail_asset_id',
        table_name='body_analysis_records',
    )
    op.drop_index(
        'ix_body_analysis_records_image_asset_id',
        table_name='body_analysis_records',
    )
    op.drop_column('body_analysis_records', 'thumbnail_asset_id')
    op.drop_column('body_analysis_records', 'image_asset_id')

    op.drop_index('ix_analysis_tasks_thumbnail_asset_id', table_name='analysis_tasks')
    op.drop_index('ix_analysis_tasks_image_asset_id', table_name='analysis_tasks')
    op.drop_column('analysis_tasks', 'thumbnail_asset_id')
    op.drop_column('analysis_tasks', 'image_asset_id')

    op.drop_index('ux_media_assets_user_checksum', table_name='media_assets')
    op.drop_index('ix_media_assets_status', table_name='media_assets')
    op.drop_index('ix_media_assets_user_id', table_name='media_assets')
    op.drop_table('media_assets')
