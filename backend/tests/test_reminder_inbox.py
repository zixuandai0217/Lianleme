"""提醒调度宿主与站内收件箱（工单 33）的外部行为测试。

覆盖：手动 tick 产生一条可读通知、同日重复 tick 幂等、tick 内无外部调用、
已读/全部已读与未读数、越权与管理员边界、调度宿主优雅启停与错误隔离。
"""

import asyncio
import datetime
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.plan.plan_service as plan_service_module
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.logging import StructuredJsonFormatter
from app.main import app
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.reminder import ReminderDelivery
from app.models.user import User
from app.services.reminder.reminder_service import ReminderService
from app.services.reminder.scheduler import ReminderScheduler

TZ = ZoneInfo("Asia/Shanghai")
# 周三 20:00（本地），已过默认提醒时刻 19:00。
TICK_AT = datetime.datetime(2026, 3, 18, 20, 0, tzinfo=TZ)
NEXT_DAY_AT = datetime.datetime(2026, 3, 19, 20, 0, tzinfo=TZ)
LOCAL_DATE = TICK_AT.date()


def week_plan(rest_days: set[int] | None = None) -> list[dict]:
    rest_days = rest_days or set()
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
            "estimated_duration": 45 if weekday not in rest_days else 0,
            "is_rest_day": weekday in rest_days,
        }
        for weekday in range(1, 8)
    ]


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    db_path = tmp_path / "reminders.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="reminder-owner", nickname="Owner")
        other = User(openid="reminder-other", nickname="Other")
        admin = User(openid="reminder-admin", nickname="Admin", is_admin=True)
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


@pytest.fixture(autouse=True)
def no_llm_calls(monkeypatch):
    """tick 内不允许任何 LLM 调用：替身一旦被调用就失败。"""
    calls: list[str] = []

    async def _forbidden(self, *args, **kwargs):  # pragma: no cover - 只应在违规时执行
        calls.append("llm")
        raise AssertionError("tick 不应调用 LLM")

    monkeypatch.setattr(plan_service_module.LLMClientFactory, "get_client", _forbidden)
    return calls


@pytest.fixture(autouse=True)
def capture_logs(caplog):
    caplog.set_level(logging.INFO)
    return caplog


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _payloads(caplog) -> list[dict]:
    formatter = StructuredJsonFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if getattr(record, "fields", None) is not None
    ]


async def tick(client, at: datetime.datetime, *, as_user: int) -> dict:
    response = await client.post(
        "/api/notifications/tick",
        params={"at": at.isoformat()},
        headers=_auth(as_user),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def inbox(client, user_id: int, **params) -> dict:
    response = await client.get(
        f"/api/notifications/{user_id}", params=params, headers=_auth(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def delivery_count(session_factory) -> int:
    async with session_factory() as session:
        return (await session.execute(select(func.count(ReminderDelivery.id)))).scalar() or 0


@pytest.mark.asyncio
async def test_manual_tick_delivers_one_readable_notification(
    client, users, active_plan, no_llm_calls
):
    """AC2 + AC4：一次 tick 写一条可读的站内通知，且 tick 内不发生 LLM/外部调用。"""
    started = datetime.datetime.now()
    summary = await tick(client, TICK_AT, as_user=users["admin"].id)
    elapsed = (datetime.datetime.now() - started).total_seconds()

    assert summary["status"] == "ok"
    assert summary["delivered"] == 1
    assert summary["failed"] == 0
    assert summary["evaluated_users"] >= 3
    assert elapsed < 5, "tick 必须在秒级预算内完成"
    assert no_llm_calls == []

    page = await inbox(client, users["owner"].id)
    assert page["total"] == 1
    assert page["unread_count"] == 1
    item = page["items"][0]
    assert item["rule_code"] == "daily_training"
    assert item["title"]
    assert item["body"]
    assert item["target_path"].startswith("/")
    assert item["is_read"] is False


@pytest.mark.asyncio
async def test_same_day_tick_is_idempotent(client, users, active_plan):
    """AC3：同一天连续 tick 两次只产生一条记录，未读数仍为 1。"""
    await tick(client, TICK_AT, as_user=users["admin"].id)
    second = await tick(client, TICK_AT + datetime.timedelta(minutes=30), as_user=users["admin"].id)

    assert second["delivered"] == 0
    assert second["duplicates"] == 1

    page = await inbox(client, users["owner"].id)
    assert page["total"] == 1
    assert page["unread_count"] == 1


@pytest.mark.asyncio
async def test_checked_in_day_produces_no_training_reminder(
    client, users, active_plan, session_factory
):
    async with session_factory() as session:
        session.add(
            WorkoutRecord(
                user_id=users["owner"].id,
                workout_date=LOCAL_DATE,
                total_sets=4,
                completed_sets=4,
                completion_rate=1.0,
                duration_minutes=40,
            )
        )
        await session.commit()

    summary = await tick(client, TICK_AT, as_user=users["admin"].id)
    assert summary["delivered"] == 0
    assert (await inbox(client, users["owner"].id))["total"] == 0


@pytest.mark.asyncio
async def test_inbox_read_and_unread_counts(client, users, active_plan):
    """AC5：单条已读减 1、全部已读归零，未读筛选只返回未读。"""
    await tick(client, TICK_AT, as_user=users["admin"].id)
    await tick(client, NEXT_DAY_AT, as_user=users["admin"].id)

    page = await inbox(client, users["owner"].id)
    assert page["total"] == 2
    assert page["unread_count"] == 2

    first_id = page["items"][0]["id"]
    read = await client.post(
        f"/api/notifications/{users['owner'].id}/{first_id}/read",
        headers=_auth(users["owner"].id),
    )
    assert read.status_code == 200
    assert read.json()["unread_count"] == 1

    unread_page = await inbox(client, users["owner"].id, unread_only="true")
    assert unread_page["total"] == 1
    assert unread_page["items"][0]["id"] != first_id

    read_all = await client.post(
        f"/api/notifications/{users['owner'].id}/read-all",
        headers=_auth(users["owner"].id),
    )
    assert read_all.status_code == 200
    assert read_all.json() == {"updated": 1, "unread_count": 0}

    assert (await inbox(client, users["owner"].id))["unread_count"] == 0


@pytest.mark.asyncio
async def test_inbox_permissions(client, users, active_plan):
    """AC5：未登录 401、读他人 403、管理员也读不到他人通知正文。"""
    await tick(client, TICK_AT, as_user=users["admin"].id)

    anonymous = await client.get(f"/api/notifications/{users['owner'].id}")
    assert anonymous.status_code == 401

    other = await client.get(
        f"/api/notifications/{users['owner'].id}", headers=_auth(users["other"].id)
    )
    assert other.status_code == 403

    admin = await client.get(
        f"/api/notifications/{users['owner'].id}", headers=_auth(users["admin"].id)
    )
    assert admin.status_code == 403

    unauthorized_tick = await client.post(
        "/api/notifications/tick", headers=_auth(users["owner"].id)
    )
    assert unauthorized_tick.status_code == 403


@pytest.mark.asyncio
async def test_scheduler_start_stop_is_graceful_and_restart_does_not_duplicate(
    session_factory, users, active_plan
):
    """AC6：宿主可启动/优雅取消，关闭后不再投递，重启后也不重复投递。"""
    scheduler = ReminderScheduler(
        session_factory=session_factory,
        interval_seconds=0.01,
        now=lambda: TICK_AT,
    )
    scheduler.start()
    assert scheduler.is_running

    # 轮询等待首个 tick 落库：tick 本身要查库，固定 sleep 会在慢机器上假失败。
    for _ in range(100):
        if await delivery_count(session_factory) >= 1:
            break
        await asyncio.sleep(0.02)

    await scheduler.stop()
    assert not scheduler.is_running

    after_stop = await delivery_count(session_factory)
    assert after_stop >= 1
    await asyncio.sleep(0.05)
    assert await delivery_count(session_factory) == after_stop

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()
    assert await delivery_count(session_factory) == after_stop


@pytest.mark.asyncio
async def test_failing_tick_is_caught_and_next_ticks_still_run(
    session_factory, users, active_plan, monkeypatch, caplog
):
    """AC1：单次 tick 抛错被捕获并记录，后续两次 tick 仍返回成功摘要。"""
    original = ReminderService.tick
    calls = {"n": 0}

    async def flaky(self, now_local):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("tick exploded")
        return await original(self, now_local)

    monkeypatch.setattr(ReminderService, "tick", flaky)

    scheduler = ReminderScheduler(
        session_factory=session_factory, interval_seconds=60, now=lambda: TICK_AT
    )
    first = await scheduler.run_once()
    assert first["status"] == "error"

    second = await scheduler.run_once()
    third = await scheduler.run_once()
    assert second["status"] == "ok"
    assert third["status"] == "ok"
    assert third["duplicates"] == 1  # 同名规则同一天只落一条

    errors = [
        payload
        for payload in _payloads(caplog)
        if payload.get("event") == "reminder.tick.failed" and payload.get("level") == "error"
    ]
    assert errors, "失败的 tick 必须留下可观测事件"


@pytest.mark.asyncio
async def test_app_lifespan_mounts_and_stops_the_scheduler():
    """AC1：应用生命周期里调度宿主处于运行态，退出时被取消。"""
    async with app.router.lifespan_context(app):
        scheduler = app.state.reminder_scheduler
        assert scheduler.is_running

    assert not scheduler.is_running
