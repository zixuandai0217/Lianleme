"""Web Push 重通道（工单 35）的外部行为测试。

覆盖 AC1-AC5：
- 订阅登记 / 状态查询 / 注销 / 未登录 401；
- 未配置 VAPID 时通道不可用、订阅被稳定错误码拒绝且站内通知不受影响；
- tick 只写一条 web_push 投递记录与一条待执行作业，tick 内零外部发送；
- 执行器成功、失效响应（订阅标记失效且后续 tick 不再投递）、可重试与重试上限；
- 同一「用户 + 规则 + 本地日期 + 通道」重复 tick 不产生第二条记录或第二个作业。

设计：路由层用 httpx ASGITransport + 依赖覆盖（prior art: test_reminder_inbox.py），
发送侧用记录调用的替身，绝不在测试里真的访问推送服务。
"""

import asyncio
import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from pywebpush import WebPushException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.notification.push_service as push_service_module
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.plan import TrainingPlan
from app.models.push import (
    PUSH_JOB_STATUS_FAILED,
    PUSH_JOB_STATUS_PENDING,
    PUSH_JOB_STATUS_SENT,
    SUBSCRIPTION_FAILURE_ENDPOINT_GONE,
    PushJob,
    PushSubscription,
)
from app.models.reminder import ReminderDelivery
from app.models.reminder_preference import ReminderPreference
from app.models.user import User
from app.services.notification.push_service import (
    SEND_OUTCOME_INVALID,
    SEND_OUTCOME_RETRYABLE,
    SEND_OUTCOME_SENT,
    PushJobExecutor,
    PushJobWorker,
    PushSendResult,
    PushTarget,
    WebPushSender,
)

TZ = ZoneInfo("Asia/Shanghai")
# 周三 20:00（本地）：已过默认提醒时刻 19:00，且仍在当日窗口内。
TICK_AT = datetime.datetime(2026, 3, 18, 20, 0, tzinfo=TZ)
NEXT_DAY_AT = datetime.datetime(2026, 3, 19, 20, 0, tzinfo=TZ)
LOCAL_DATE = TICK_AT.date()


def week_plan() -> list[dict]:
    return [
        {
            "day": weekday,
            "focus": "胸背",
            "exercises": [
                {
                    "name": "卧推",
                    "sets": 4,
                    "reps": "8-12",
                    "weight_suggestion": "体重 40%",
                    "tips": "肩胛收紧",
                    "rest_seconds": 90,
                }
            ],
            "estimated_duration": 45,
            "is_rest_day": False,
        }
        for weekday in range(1, 8)
    ]


class FakePushSender:
    """记录调用的发送替身；按队列返回预设结果，默认为成功。"""

    def __init__(self, outcomes: list[PushSendResult] | None = None):
        self.outcomes = list(outcomes or [])
        self.calls: list[dict] = []

    def send(self, subscription, payload) -> PushSendResult:
        self.calls.append({"subscription": subscription, "payload": payload})
        if self.outcomes:
            return self.outcomes.pop(0)
        return PushSendResult(SEND_OUTCOME_SENT)


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    db_path = tmp_path / "push.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="push-owner", nickname="Owner")
        other = User(openid="push-other", nickname="Other")
        admin = User(openid="push-admin", nickname="Admin", is_admin=True)
        session.add_all([owner, other, admin])
        await session.commit()
        for user in (owner, other, admin):
            await session.refresh(user)
        return {"owner": owner, "other": other, "admin": admin}


@pytest_asyncio.fixture
async def active_plan(session_factory, users):
    async with session_factory() as session:
        plan = TrainingPlan(
            user_id=users["owner"].id,
            week_start=LOCAL_DATE,
            weekly_plan=week_plan(),
            difficulty_factor=1.0,
            status="active",
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
def push_configured(monkeypatch):
    """打开通道：三项 VAPID 配置齐全时通道才可用。"""
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "test-public-key")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "test-private-key")
    monkeypatch.setattr(settings, "VAPID_SUBJECT", "mailto:ops@example.com")


@pytest.fixture(autouse=True)
def no_external_webpush(monkeypatch):
    """tick 内绝不允许触碰真实推送服务；一旦调用 webpush 即失败。"""
    calls: list[None] = []

    def _forbidden(*args, **kwargs):  # pragma: no cover - 只应在违规时执行
        calls.append(None)
        raise AssertionError("tick 不应调用 Web Push 发送器")

    monkeypatch.setattr(push_service_module, "webpush", _forbidden)
    return calls


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


SUBSCRIBE_BODY = {
    "endpoint": "https://push.example.com/subscription/abc",
    "keys": {"p256dh": "p256dh-key", "auth": "auth-secret"},
}


async def subscribe(client, user_id: int, body: dict | None = None):
    return await client.post(
        "/api/notifications/push/subscribe",
        json=body or SUBSCRIBE_BODY,
        headers=_auth(user_id),
    )


async def push_status(client, user_id: int) -> dict:
    response = await client.get(
        "/api/notifications/push/status", headers=_auth(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def tick(client, at: datetime.datetime, *, as_user: int) -> dict:
    response = await client.post(
        "/api/notifications/tick",
        params={"at": at.isoformat()},
        headers=_auth(as_user),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def inbox(client, user_id: int) -> dict:
    response = await client.get(
        f"/api/notifications/{user_id}", headers=_auth(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def seed_subscription(session_factory, user_id: int, endpoint: str) -> int:
    """绕过路由直接落一条有效订阅（用于测试通道打开但先登记的历史数据）。"""
    async with session_factory() as session:
        row = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh="p256dh-key",
            auth="auth-secret",
            is_active=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def channel_counts(session_factory, user_id: int) -> dict:
    async with session_factory() as session:
        in_app = (
            await session.execute(
                select(func.count())
                .select_from(ReminderDelivery)
                .where(
                    ReminderDelivery.user_id == user_id,
                    ReminderDelivery.channel == "in_app",
                    ReminderDelivery.status == "sent",
                )
            )
        ).scalar() or 0
        web_push = (
            await session.execute(
                select(func.count())
                .select_from(ReminderDelivery)
                .where(
                    ReminderDelivery.user_id == user_id,
                    ReminderDelivery.channel == "web_push",
                )
            )
        ).scalar() or 0
        jobs = (
            await session.execute(
                select(func.count())
                .select_from(PushJob)
                .where(PushJob.user_id == user_id)
            )
        ).scalar() or 0
        subscriptions = (
            await session.execute(
                select(func.count())
                .select_from(PushSubscription)
                .where(PushSubscription.user_id == user_id)
            )
        ).scalar() or 0
        return {
            "in_app": int(in_app),
            "web_push": int(web_push),
            "jobs": int(jobs),
            "subscriptions": int(subscriptions),
        }


async def get_web_push_delivery(session_factory, user_id: int) -> ReminderDelivery | None:
    async with session_factory() as session:
        return (
            await session.execute(
                select(ReminderDelivery)
                .where(
                    ReminderDelivery.user_id == user_id,
                    ReminderDelivery.channel == "web_push",
                )
                .order_by(ReminderDelivery.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()


async def get_job(session_factory, user_id: int) -> PushJob:
    async with session_factory() as session:
        return (
            await session.execute(
                select(PushJob)
                .where(PushJob.user_id == user_id)
                .order_by(PushJob.id.desc())
                .limit(1)
            )
        ).scalar_one()


async def get_subscription(session_factory, subscription_id: int) -> PushSubscription:
    async with session_factory() as session:
        return await session.get(PushSubscription, subscription_id)


def _executor(session_factory, sender: FakePushSender, **kwargs) -> PushJobExecutor:
    return PushJobExecutor(sender=sender, session_factory=session_factory, **kwargs)


# ---------- AC1 订阅登记 / 状态 / 注销 / 401 ----------


@pytest.mark.asyncio
async def test_subscribe_status_and_unsubscribe(client, users, session_factory, push_configured):
    """AC1：登记后状态为已订阅，注销后为未订阅，订阅行仍保留但失效。"""
    initial = await push_status(client, users["owner"].id)
    assert initial == {
        "available": True,
        "subscribed": False,
        "subscription_count": 0,
        "public_key": "test-public-key",
    }

    response = await subscribe(client, users["owner"].id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subscribed"] is True
    assert body["subscription_count"] == 1
    assert body["subscription_id"] > 0

    after = await push_status(client, users["owner"].id)
    assert after == {
        "available": True,
        "subscribed": True,
        "subscription_count": 1,
        "public_key": "test-public-key",
    }

    removed = await client.delete(
        "/api/notifications/push/subscribe", headers=_auth(users["owner"].id)
    )
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"subscribed": False, "deactivated": 1}

    final = await push_status(client, users["owner"].id)
    assert final == {
        "available": True,
        "subscribed": False,
        "subscription_count": 0,
        "public_key": "test-public-key",
    }

    # 注销是软失效：行还在，但 is_active=False，后续 tick 不会为它投递。
    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts["subscriptions"] == 1


@pytest.mark.asyncio
async def test_resubscribe_same_endpoint_reactivates_without_duplicate(
    client, users, session_factory, push_configured
):
    """同一 endpoint 重复登记是 upsert：只有一行且重新激活。"""
    await subscribe(client, users["owner"].id)
    await client.delete(
        "/api/notifications/push/subscribe", headers=_auth(users["owner"].id)
    )

    again = await subscribe(
        client,
        users["owner"].id,
        {
            "endpoint": SUBSCRIBE_BODY["endpoint"],
            "keys": {"p256dh": "new-p256dh", "auth": "new-auth"},
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["subscription_count"] == 1

    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts["subscriptions"] == 1

    subscription = await get_subscription(
        session_factory, again.json()["subscription_id"]
    )
    assert subscription.is_active is True
    assert subscription.p256dh == "new-p256dh"
    assert subscription.auth == "new-auth"


@pytest.mark.asyncio
async def test_subscriptions_are_scoped_to_token_owner(
    client, users, session_factory, push_configured
):
    """他人订阅不进入我的状态；注销只影响本人的订阅。"""
    await subscribe(client, users["owner"].id)
    await subscribe(
        client,
        users["other"].id,
        {
            "endpoint": "https://push.example.com/subscription/other",
            "keys": {"p256dh": "other-p256dh", "auth": "other-auth"},
        },
    )

    assert (await push_status(client, users["owner"].id))["subscription_count"] == 1
    assert (await push_status(client, users["other"].id))["subscription_count"] == 1

    await client.delete(
        "/api/notifications/push/subscribe", headers=_auth(users["owner"].id)
    )
    assert (await push_status(client, users["owner"].id))["subscribed"] is False
    assert (await push_status(client, users["other"].id))["subscribed"] is True


@pytest.mark.asyncio
async def test_push_endpoints_require_authentication(client, users):
    """AC1：未登录访问状态/登记/注销一律 401。"""
    status = await client.get("/api/notifications/push/status")
    assert status.status_code == 401

    created = await client.post("/api/notifications/push/subscribe", json=SUBSCRIBE_BODY)
    assert created.status_code == 401

    removed = await client.delete("/api/notifications/push/subscribe")
    assert removed.status_code == 401


# ---------- AC2 未配置密钥：通道不可用且不影响站内 ----------


@pytest.mark.asyncio
async def test_unavailable_channel_rejects_subscribe_and_keeps_inbox_working(
    client, users, active_plan, session_factory, monkeypatch
):
    """AC2：没有 VAPID 时状态不可用、订阅被稳定错误码拒绝且不落行；站内照常。"""
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(settings, "VAPID_SUBJECT", "")

    status = await push_status(client, users["owner"].id)
    assert status == {
        "available": False,
        "subscribed": False,
        "subscription_count": 0,
        "public_key": None,
    }

    rejected = await subscribe(client, users["owner"].id)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "push_unavailable"
    assert (await channel_counts(session_factory, users["owner"].id))["subscriptions"] == 0

    summary = await tick(client, TICK_AT, as_user=users["admin"].id)
    assert summary["delivered"] == 1
    assert (await inbox(client, users["owner"].id))["unread_count"] == 1
    assert (await channel_counts(session_factory, users["owner"].id))["web_push"] == 0


# ---------- AC3 tick 只写记录与作业，零发送 ----------


@pytest.mark.asyncio
async def test_tick_enqueues_one_web_push_delivery_and_job_without_sending(
    client, users, active_plan, session_factory, push_configured, no_external_webpush
):
    """AC3：tick 写一条 pending 的 web_push 记录 + 一条 pending 作业，发送次数为 0。"""
    subscribed = await subscribe(client, users["owner"].id)
    subscription_id = subscribed.json()["subscription_id"]

    summary = await tick(client, TICK_AT, as_user=users["admin"].id)
    assert summary["delivered"] == 1
    assert no_external_webpush == []

    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts == {"in_app": 1, "web_push": 1, "jobs": 1, "subscriptions": 1}

    delivery = await get_web_push_delivery(session_factory, users["owner"].id)
    assert delivery.status == "pending"
    assert delivery.rule_code == "daily_training"
    assert delivery.payload["title"]
    assert delivery.payload["body"]
    assert delivery.payload["target_path"].startswith("/")

    job = await get_job(session_factory, users["owner"].id)
    assert job.status == PUSH_JOB_STATUS_PENDING
    assert job.attempts == 0
    assert job.delivery_id == delivery.id
    assert job.subscription_id == subscription_id


@pytest.mark.asyncio
async def test_tick_skips_push_without_active_subscription(
    client, users, active_plan, session_factory, push_configured
):
    """通道可用但用户没有有效订阅：只写站内记录，不投递推送作业。"""
    summary = await tick(client, TICK_AT, as_user=users["admin"].id)
    assert summary["delivered"] == 1

    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts["in_app"] == 1
    assert counts["web_push"] == 0
    assert counts["jobs"] == 0


@pytest.mark.asyncio
async def test_inactive_subscription_does_not_get_new_push_deliveries(
    client, users, active_plan, session_factory, push_configured
):
    """失效订阅不参与后续 tick 投递。"""
    await seed_subscription(
        session_factory, users["owner"].id, "https://push.example.com/inactive"
    )
    async with session_factory() as session:
        row = (
            await session.execute(
                select(PushSubscription).where(
                    PushSubscription.user_id == users["owner"].id
                )
            )
        ).scalar_one()
        row.is_active = False
        await session.commit()

    await tick(client, TICK_AT, as_user=users["admin"].id)
    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts["in_app"] == 1
    assert counts["web_push"] == 0
    assert counts["jobs"] == 0


@pytest.mark.asyncio
async def test_skipped_candidate_does_not_enqueue_push_job(
    client, users, active_plan, session_factory, push_configured
):
    """被每日上限裁掉的候选只留跳过记录，不产生 web_push 记录或作业。"""
    await subscribe(client, users["owner"].id)
    async with session_factory() as session:
        session.add(ReminderPreference(user_id=users["owner"].id, daily_cap=0))
        await session.commit()

    summary = await tick(client, TICK_AT, as_user=users["admin"].id)
    assert summary["delivered"] == 0
    assert summary["skipped"] >= 1

    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts["in_app"] == 0
    assert counts["web_push"] == 0
    assert counts["jobs"] == 0


# ---------- AC5 重复 tick 的幂等 ----------


@pytest.mark.asyncio
async def test_duplicate_tick_does_not_duplicate_delivery_or_job(
    client, users, active_plan, session_factory, push_configured
):
    """AC5：重复 tick 只命中唯一键，不产生第二条 web_push 记录或第二个作业。"""
    await subscribe(client, users["owner"].id)

    await tick(client, TICK_AT, as_user=users["admin"].id)
    second = await tick(
        client, TICK_AT + datetime.timedelta(minutes=30), as_user=users["admin"].id
    )

    assert second["delivered"] == 0
    assert second["duplicates"] == 1
    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts == {"in_app": 1, "web_push": 1, "jobs": 1, "subscriptions": 1}


# ---------- AC4 执行器：成功 / 失效 / 重试上限 ----------


@pytest.mark.asyncio
async def test_executor_success_marks_delivery_and_job_sent(
    client, users, active_plan, session_factory, push_configured
):
    """AC4：发送成功后投递记录与作业均为已发送，订阅记录最后成功时间。"""
    subscribed = await subscribe(client, users["owner"].id)
    subscription_id = subscribed.json()["subscription_id"]
    await tick(client, TICK_AT, as_user=users["admin"].id)

    sender = FakePushSender()
    result = await _executor(session_factory, sender).run_once()
    assert result["sent"] == 1
    assert len(sender.calls) == 1

    delivery = await get_web_push_delivery(session_factory, users["owner"].id)
    assert delivery.status == "sent"
    job = await get_job(session_factory, users["owner"].id)
    assert job.status == PUSH_JOB_STATUS_SENT

    subscription = await get_subscription(session_factory, subscription_id)
    assert subscription.last_success_at is not None
    assert subscription.is_active is True

    # 发送载荷只带通知本身的三个字段，不泄漏订阅密钥。
    assert set(sender.calls[0]["payload"]) == {"title", "body", "target_path"}
    assert sender.calls[0]["subscription"].endpoint == SUBSCRIBE_BODY["endpoint"]


@pytest.mark.asyncio
async def test_executor_invalid_response_fails_delivery_and_deactivates_subscription(
    client, users, active_plan, session_factory, push_configured
):
    """AC4：404/410 失效响应 → 记录失败、订阅失效，后续 tick 不再投递。"""
    subscribed = await subscribe(client, users["owner"].id)
    subscription_id = subscribed.json()["subscription_id"]
    await tick(client, TICK_AT, as_user=users["admin"].id)

    sender = FakePushSender([PushSendResult(SEND_OUTCOME_INVALID, "http_410")])
    result = await _executor(session_factory, sender).run_once()
    assert result["failed"] == 1
    assert len(sender.calls) == 1

    delivery = await get_web_push_delivery(session_factory, users["owner"].id)
    assert delivery.status == "failed"
    job = await get_job(session_factory, users["owner"].id)
    assert job.status == PUSH_JOB_STATUS_FAILED

    subscription = await get_subscription(session_factory, subscription_id)
    assert subscription.is_active is False
    assert subscription.failure_reason == SUBSCRIPTION_FAILURE_ENDPOINT_GONE

    # 第二天照常产生站内通知，但失效订阅不会再产生 web_push 记录/作业。
    await tick(client, NEXT_DAY_AT, as_user=users["admin"].id)
    counts = await channel_counts(session_factory, users["owner"].id)
    assert counts["in_app"] == 2
    assert counts["web_push"] == 1
    assert counts["jobs"] == 1


@pytest.mark.asyncio
async def test_executor_retryable_failure_keeps_job_pending_until_cap(
    client, users, active_plan, session_factory, push_configured
):
    """可重试失败累计尝试次数；达到上限后作业与投递记录一并失败。"""
    await subscribe(client, users["owner"].id)
    await tick(client, TICK_AT, as_user=users["admin"].id)

    sender = FakePushSender(
        [
            PushSendResult(SEND_OUTCOME_RETRYABLE, "timeout"),
            PushSendResult(SEND_OUTCOME_RETRYABLE, "timeout"),
        ]
    )
    executor = _executor(session_factory, sender, max_attempts=2)

    first = await executor.run_once()
    assert first["retried"] == 1
    job = await get_job(session_factory, users["owner"].id)
    assert job.status == PUSH_JOB_STATUS_PENDING
    assert job.attempts == 1
    assert (await get_web_push_delivery(session_factory, users["owner"].id)).status == "pending"

    second = await executor.run_once()
    assert second["failed"] == 1
    job = await get_job(session_factory, users["owner"].id)
    assert job.status == PUSH_JOB_STATUS_FAILED
    assert job.attempts == 2
    assert (await get_web_push_delivery(session_factory, users["owner"].id)).status == "failed"
    assert len(sender.calls) == 2

    # 作业已到终态，再跑一次不会重复发送。
    third = await executor.run_once()
    assert third["claimed"] == 0
    assert len(sender.calls) == 2


@pytest.mark.asyncio
async def test_executor_skips_inactive_subscription_without_sending(
    client, users, active_plan, session_factory, push_configured
):
    """执行前订阅已被注销：作业直接失败，不调用发送器。"""
    await subscribe(client, users["owner"].id)
    await tick(client, TICK_AT, as_user=users["admin"].id)
    await client.delete(
        "/api/notifications/push/subscribe", headers=_auth(users["owner"].id)
    )

    sender = FakePushSender()
    result = await _executor(session_factory, sender).run_once()
    assert result["failed"] == 1
    assert sender.calls == []
    assert (await get_job(session_factory, users["owner"].id)).status == PUSH_JOB_STATUS_FAILED


@pytest.mark.asyncio
async def test_worker_loop_sends_and_stops_gracefully(
    client, users, active_plan, session_factory, push_configured
):
    """后台 worker 循环执行作业；stop 后不再发送，重启也不会重复发送。"""
    await subscribe(client, users["owner"].id)
    await tick(client, TICK_AT, as_user=users["admin"].id)

    sender = FakePushSender()
    worker = PushJobWorker(
        session_factory=session_factory,
        sender=sender,
        interval_seconds=0.01,
    )
    worker.start()
    assert worker.is_running

    for _ in range(100):
        job = await get_job(session_factory, users["owner"].id)
        if job.status == PUSH_JOB_STATUS_SENT:
            break
        await asyncio.sleep(0.02)

    await worker.stop()
    assert not worker.is_running

    job = await get_job(session_factory, users["owner"].id)
    assert job.status == PUSH_JOB_STATUS_SENT
    sent_calls = len(sender.calls)
    assert sent_calls == 1

    worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()
    assert len(sender.calls) == sent_calls


# ---------- 生产发送器：pywebpush 调用与失效状态映射 ----------


def _target() -> PushTarget:
    return PushTarget(
        subscription_id=1,
        endpoint=SUBSCRIBE_BODY["endpoint"],
        p256dh="p256dh-key",
        auth="auth-secret",
    )


def test_web_push_sender_uses_pywebpush_with_vapid_and_notification_payload(monkeypatch):
    """生产发送器真的走 pywebpush，且只序列化通知三字段。"""
    captured: dict = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(push_service_module, "webpush", _capture)
    sender = WebPushSender(private_key="private-key", subject="mailto:ops@example.com")

    result = sender.send(
        _target(), {"title": "T", "body": "B", "target_path": "/notifications"}
    )

    assert result == PushSendResult(SEND_OUTCOME_SENT)
    assert captured["vapid_private_key"] == "private-key"
    assert captured["vapid_claims"] == {"sub": "mailto:ops@example.com"}
    assert captured["subscription_info"] == {
        "endpoint": SUBSCRIBE_BODY["endpoint"],
        "keys": {"p256dh": "p256dh-key", "auth": "auth-secret"},
    }
    assert json.loads(captured["data"]) == {
        "title": "T",
        "body": "B",
        "target_path": "/notifications",
    }


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (404, PushSendResult(SEND_OUTCOME_INVALID, "http_404")),
        (410, PushSendResult(SEND_OUTCOME_INVALID, "http_410")),
        (503, PushSendResult(SEND_OUTCOME_RETRYABLE, "http_503")),
    ],
)
def test_web_push_sender_maps_provider_status(monkeypatch, status_code, expected):
    """404/410 是永久失效；其余状态是可重试失败。"""

    def _raise(**kwargs):
        raise WebPushException("push failed", response=SimpleNamespace(status_code=status_code))

    monkeypatch.setattr(push_service_module, "webpush", _raise)
    sender = WebPushSender(private_key="private-key", subject="mailto:ops@example.com")

    assert sender.send(_target(), {"title": "T", "body": "B", "target_path": "/x"}) == expected


def test_web_push_sender_maps_transport_error_to_retryable(monkeypatch):
    """网络/证书等异常按可重试处理，且落库的是异常类名而不是原文。"""

    def _raise(**kwargs):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(push_service_module, "webpush", _raise)
    sender = WebPushSender(private_key="private-key", subject="mailto:ops@example.com")

    result = sender.send(_target(), {"title": "T", "body": "B", "target_path": "/x"})
    assert result == PushSendResult(SEND_OUTCOME_RETRYABLE, "RuntimeError")


@pytest.mark.asyncio
async def test_endpoint_already_owned_by_another_user_is_rejected(
    client, users, session_factory, push_configured
):
    """同一 endpoint 换账号登记：拒绝静默转移归属，原账号的订阅保持不变。"""
    first = await subscribe(client, users["owner"].id)
    assert first.status_code == 200, first.text
    subscription_id = first.json()["subscription_id"]

    takeover = await subscribe(client, users["other"].id)
    assert takeover.status_code == 409, takeover.text
    assert takeover.json()["detail"]["code"] == "push_endpoint_in_use"

    subscription = await get_subscription(session_factory, subscription_id)
    assert subscription.user_id == users["owner"].id
    assert subscription.is_active is True


@pytest.mark.asyncio
async def test_executor_never_sends_a_job_to_another_users_endpoint(
    client, users, active_plan, session_factory, push_configured
):
    """作业与订阅归属不一致时拒绝发送：不能把 A 的通知推到 B 的设备。"""
    subscribed = await subscribe(client, users["owner"].id)
    subscription_id = subscribed.json()["subscription_id"]
    await tick(client, TICK_AT, as_user=users["admin"].id)

    # 模拟历史脏数据 / 跨账号接管：订阅被改挂到另一个用户。
    async with session_factory() as session:
        subscription = await session.get(PushSubscription, subscription_id)
        assert subscription is not None
        subscription.user_id = users["other"].id
        await session.commit()

    sender = FakePushSender()
    result = await _executor(session_factory, sender).run_once()
    assert sender.calls == []
    assert result["failed"] == 1

    job = await get_job(session_factory, users["owner"].id)
    assert job.status == "failed"
    delivery = await get_web_push_delivery(session_factory, users["owner"].id)
    assert delivery.status == "failed"
