"""chat_message_actions_state：助手消息的动作快照与教练状态（工单 18）

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-02

快捷动作与教练状态从「模型自述 / 前端写死」改为服务端确定性规划，并且必须进入
持久化：重新进入陪练页时，历史助手消息要能带回**当时**的按钮与状态，不能在读取
时按今天的训练上下文重新规划（那样按钮会跟着上下文漂移）。

- ``actions``（JSONB，可空）：``[{label, prompt}]`` 快照，最多四条；
- ``coach_state``（String(16)，可空）：guide / count / rest / complete。

两列都允许为空：旧消息没有快照，读取时降级为空列表 / None，页面只显示正文。
DDL 与 ``app/models/chat_message.py`` 逐列对齐（ORM 是唯一事实源），
downgrade 只丢弃本 revision 追加的两列。
"""
import sqlalchemy as sa

from alembic import op
from app.core.compat import JSONB

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'chat_messages',
        sa.Column('actions', JSONB, nullable=True),
    )
    op.add_column(
        'chat_messages',
        sa.Column('coach_state', sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('chat_messages', 'coach_state')
    op.drop_column('chat_messages', 'actions')
