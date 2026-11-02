"""站内通知路由：收件箱读取/已读，以及内部手动 tick 入口（工单 33）。

全部接口要求登录且只能操作本人数据；管理员不得读取任何用户的通知正文——管理端只有
聚合只读，因此手动 tick 是唯一的管理员入口，且它不返回任何通知内容。
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.local_time import local_now, to_local
from app.core.security import ensure_current_user_matches, get_current_admin, get_current_user
from app.models.user import User
from app.schemas.notification import (
    MarkAllReadResponse,
    MarkReadResponse,
    NotificationItem,
    NotificationListResponse,
    TickSummaryResponse,
)
from app.services.reminder.reminder_service import ReminderService

router = APIRouter()


def _to_item(delivery) -> NotificationItem:
    payload = delivery.payload or {}
    return NotificationItem(
        id=delivery.id,
        rule_code=delivery.rule_code,
        title=str(payload.get("title") or ""),
        body=str(payload.get("body") or ""),
        target_path=str(payload.get("target_path") or "/dashboard"),
        created_at=delivery.created_at,
        read_at=delivery.read_at,
        is_read=delivery.read_at is not None,
    )


@router.post("/tick", response_model=TickSummaryResponse)
async def manual_tick(
    at: datetime.datetime | None = Query(
        default=None,
        description="可选的注入时刻（运维/测试用）：不带时区按 UTC 解释，再换算到部署本地时区",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """手动触发一次提醒 tick（内部/运维用途，不对外公开）。"""
    ran_at = to_local(at) if at is not None else local_now()
    service = ReminderService(db)
    summary = await service.tick(ran_at)
    return TickSummaryResponse(
        status=summary.status,
        evaluated_users=summary.evaluated_users,
        delivered=summary.delivered,
        duplicates=summary.duplicates,
        failed=summary.failed,
        ran_at=ran_at,
    )


@router.get("/{user_id}", response_model=NotificationListResponse)
async def list_notifications(
    user_id: int,
    unread_only: bool = Query(default=False, description="只看未读"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """站内通知列表；返回全量未读数，供铃铛角标使用。"""
    ensure_current_user_matches(current_user, user_id)
    service = ReminderService(db)
    rows, total, unread = await service.list_notifications(
        user_id, unread_only=unread_only, page=page, page_size=page_size
    )
    return NotificationListResponse(
        items=[_to_item(row) for row in rows],
        total=total,
        unread_count=unread,
        page=page,
        page_size=page_size,
    )


@router.post("/{user_id}/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把本人全部未读通知标为已读。"""
    ensure_current_user_matches(current_user, user_id)
    service = ReminderService(db)
    updated = await service.mark_all_read(user_id, now=datetime.datetime.now(datetime.timezone.utc))
    return MarkAllReadResponse(updated=updated, unread_count=await service.unread_count(user_id))


@router.post("/{user_id}/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_read(
    user_id: int,
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把单条通知标为已读；已读重复提交保持幂等。"""
    ensure_current_user_matches(current_user, user_id)
    service = ReminderService(db)
    now = datetime.datetime.now(datetime.timezone.utc)
    delivery = await service.mark_read(user_id, notification_id, now=now)
    if delivery is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "notification_not_found", "message": "找不到这条通知"},
        )
    return MarkReadResponse(
        notification_id=delivery.id,
        read_at=delivery.read_at or now,
        unread_count=await service.unread_count(user_id),
    )
