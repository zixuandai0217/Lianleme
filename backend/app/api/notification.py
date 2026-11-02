"""站内通知路由：收件箱读取/已读，以及内部手动 tick 入口（工单 33）。

全部接口要求登录且只能操作本人数据；管理员不得读取任何用户的通知正文——管理端只有
聚合只读，因此手动 tick 是唯一的管理员入口，且它不返回任何通知内容。
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.local_time import local_now, to_local
from app.core.security import ensure_current_user_matches, get_current_admin, get_current_user
from app.models.user import User
from app.schemas.notification import (
    DeliveryRecordItem,
    DeliveryRecordListResponse,
    DeliveryStatus,
    MarkAllReadResponse,
    MarkReadResponse,
    NotificationItem,
    NotificationListResponse,
    PushStatusResponse,
    PushSubscribeRequest,
    PushSubscribeResponse,
    PushUnsubscribeResponse,
    ReminderPreferenceResponse,
    ReminderPreferenceUpdate,
    TickSummaryResponse,
)
from app.services.notification.push_service import (
    ERROR_CODE_PUSH_ENDPOINT_IN_USE,
    ERROR_CODE_PUSH_UNAVAILABLE,
    PushEndpointInUse,
    PushService,
)
from app.services.reminder import preferences as preference_service
from app.services.reminder.reminder_service import ReminderService

router = APIRouter()

# 未配置 VAPID 时登记订阅的稳定错误码与安全文案。
PUSH_UNAVAILABLE_MESSAGE = "推送通道未配置，暂不可用"


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


@router.get("/push/status", response_model=PushStatusResponse)
async def get_push_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前身份的推送通道状态；未配置密钥时 available=false（站内不受影响）。"""
    service = PushService(db)
    count = await service.active_subscription_count(current_user.id)
    return PushStatusResponse(
        available=service.available,
        subscribed=count > 0,
        subscription_count=count,
        public_key=settings.VAPID_PUBLIC_KEY.strip() if service.available else None,
    )


@router.post("/push/subscribe", response_model=PushSubscribeResponse)
async def subscribe_push(
    payload: PushSubscribeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """登记浏览器推送订阅；同一 endpoint 重复登记是 upsert，不会产生第二行。

    通道未配置时必须在写入之前拒绝：数据库里不允许留下一条永远不会被投递的订阅。
    """
    service = PushService(db)
    if not service.available:
        raise HTTPException(
            status_code=409,
            detail={"code": ERROR_CODE_PUSH_UNAVAILABLE, "message": PUSH_UNAVAILABLE_MESSAGE},
        )
    try:
        row = await service.subscribe(
            current_user.id,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
        )
    except PushEndpointInUse:
        raise HTTPException(
            status_code=409,
            detail={
                "code": ERROR_CODE_PUSH_ENDPOINT_IN_USE,
                "message": "该浏览器已绑定其他账号，请先在原账号注销推送",
            },
        ) from None
    count = await service.active_subscription_count(current_user.id)
    return PushSubscribeResponse(
        subscribed=True,
        subscription_id=row.id,
        subscription_count=count,
    )


@router.delete("/push/subscribe", response_model=PushUnsubscribeResponse)
async def unsubscribe_push(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """注销本人全部推送订阅（软失效）；返回本次失效条数。"""
    deactivated = await PushService(db).deactivate_all(current_user.id)
    return PushUnsubscribeResponse(subscribed=False, deactivated=deactivated)


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
        skipped=summary.skipped,
        failed=summary.failed,
        ran_at=ran_at,
    )


@router.get("/deliveries", response_model=DeliveryRecordListResponse)
async def list_deliveries(
    user_id: int | None = Query(default=None, description="只看某个用户的投递记录"),
    status: DeliveryStatus | None = Query(default=None, description="sent / skipped / failed"),
    date_from: datetime.date | None = Query(default=None, description="本地日期下界（含）"),
    date_to: datetime.date | None = Query(default=None, description="本地日期上界（含）"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """投递记录查询（内部/运维用途，含被跳过的候选与原因，不返回通知正文）。"""
    service = ReminderService(db)
    rows, total = await service.list_deliveries(
        user_id=user_id,
        status=status,
        local_date_from=date_from,
        local_date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return DeliveryRecordListResponse(
        items=[
            DeliveryRecordItem(
                id=row.id,
                user_id=row.user_id,
                rule_code=row.rule_code,
                local_date=row.local_date,
                channel=row.channel,
                status=row.status,
                skip_reason=(row.payload or {}).get("skip_reason"),
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
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


def _to_preference_response(row) -> ReminderPreferenceResponse:
    return ReminderPreferenceResponse(
        daily_training_enabled=row.daily_training_enabled,
        rest_day_note_enabled=row.rest_day_note_enabled,
        recall_inactive_enabled=row.recall_inactive_enabled,
        weekly_goal_enabled=row.weekly_goal_enabled,
        onboarding_nudge_enabled=row.onboarding_nudge_enabled,
        quiet_hours_start=row.quiet_hours_start,
        quiet_hours_end=row.quiet_hours_end,
        daily_cap=row.daily_cap,
        weekly_goal_target=row.weekly_goal_target,
        timezone=row.timezone,
    )


@router.get("/{user_id}/preferences", response_model=ReminderPreferenceResponse)
async def get_preferences(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取提醒偏好；从未保存过时返回缺省值（读路径不写库）。"""
    ensure_current_user_matches(current_user, user_id)
    return _to_preference_response(await preference_service.get_effective(db, user_id))


@router.put("/{user_id}/preferences", response_model=ReminderPreferenceResponse)
async def update_preferences(
    user_id: int,
    payload: ReminderPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """整份替换提醒偏好；非法值在写入前被 422 拒绝，已存偏好保持不变。"""
    ensure_current_user_matches(current_user, user_id)
    row = await preference_service.upsert(db, user_id, payload.model_dump())
    return _to_preference_response(row)


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
