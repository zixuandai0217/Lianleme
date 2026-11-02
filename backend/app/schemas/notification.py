"""站内通知（收件箱）与提醒 tick 的对外形状（工单 33）。"""
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NotificationItem(BaseModel):
    """一条站内通知（由投递记录投影而来）。"""

    id: int
    rule_code: str = Field(..., description="触发这条通知的规则代码")
    title: str
    body: str
    target_path: str = Field(..., description="点击后应跳转的站内路径")
    created_at: datetime.datetime
    read_at: Optional[datetime.datetime] = None
    is_read: bool


class NotificationListResponse(BaseModel):
    """收件箱一页；``unread_count`` 是全量未读数，不是本页未读数。"""

    items: List[NotificationItem]
    total: int
    unread_count: int
    page: int
    page_size: int


class MarkReadResponse(BaseModel):
    notification_id: int
    read_at: datetime.datetime
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated: int
    unread_count: int


class TickSummaryResponse(BaseModel):
    """一次手动 tick 的摘要（内部/运维入口）。"""

    status: str
    evaluated_users: int
    delivered: int
    duplicates: int
    failed: int
    ran_at: datetime.datetime
