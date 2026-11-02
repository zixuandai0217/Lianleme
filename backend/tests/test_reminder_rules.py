"""六条提醒规则、每日上限与免打扰（工单 34）的路由层行为测试。

所有用例都通过「手动 tick + 收件箱接口」观察结果；跳过记录按 AC4/AC5 的要求
直接读投递记录（状态与原因就是这条契约的一部分）。
"""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.reminder import ReminderDelivery
from app.models.user import User

TZ = ZoneInfo("Asia/Shanghai")
# 周三 20:00（本地）：已过默认提醒时刻 19:00，且在当日窗口 [19:00, 23:00) 内。
WEDNESDAY = datetime.datetime(2026, 3, 18, 20, 0, tzinfo=TZ)
THURSDAY = datetime.datetime(2026, 3, 19, 20, 0, tzinfo=TZ)
SUNDAY = datetime.datetime(2026, 3, 22, 20, 0, tzinfo=TZ)
TODAY = WEDNESDAY.date()
WEEK_START = TODAY - datetime.timedelta(days=TODAY.weekday())


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
    db_path = tmp_path / "reminder-rules.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


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


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _created_at(days_ago: int) -> datetime.datetime:
    """Registration moment relative to the frozen local today (UTC storage)."""
    return datetime.datetime.combine(
        TODAY - datetime.timedelta(days=days_ago), datetime.time(9, 0), tzinfo=TZ
    ).astimezone(datetime.timezone.utc)


async def seed_user(
    factory,
    *,
    openid: str,
    days_ago: int = 8,
    has_analysis: bool = True,
    admin: bool = False,
) -> User:
    async with factory() as session:
        user = User(
            openid=openid,
            nickname=openid,
            is_admin=admin,
            created_at=_created_at(days_ago),
            body_analysis={"body_type": "mesomorph"} if has_analysis else None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def seed_plan(factory, user_id: int, *, rest_days: set[int] | None = None) -> TrainingPlan:
    async with factory() as session:
        plan = TrainingPlan(
            user_id=user_id,
            week_start=WEEK_START,
            weekly_plan=week_plan(rest_days),
            difficulty_factor=1.0,
            status="active",
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


async def seed_checkins(factory, user_id: int, dates: list[datetime.date]) -> None:
    async with factory() as session:
        for workout_date in dates:
            session.add(
                WorkoutRecord(
                    user_id=user_id,
                    workout_date=workout_date,
                    total_sets=4,
                    completed_sets=4,
                    completion_rate=1.0,
                    duration_minutes=40,
                )
            )
        await session.commit()


async def seed_delivery(
    factory,
    user_id: int,
    *,
    rule_code: str,
    local_date: datetime.date,
    status: str = 'sent',
) -> None:
    """Seed a historical delivery row (e.g. yesterday's reminder)."""
    async with factory() as session:
        session.add(
            ReminderDelivery(
                user_id=user_id,
                rule_code=rule_code,
                local_date=local_date,
                channel='in_app',
                status=status,
                payload={'title': 't', 'body': 'b', 'target_path': '/'},
            )
        )
        await session.commit()


async def seed_preferences(factory, user_id: int, **values) -> None:
    """Seed a preference row directly (the API path is covered by its own cases)."""
    from app.models.reminder_preference import ReminderPreference

    async with factory() as session:
        session.add(ReminderPreference(user_id=user_id, **values))
        await session.commit()


async def run_tick(client, admin_id: int, at: datetime.datetime) -> dict:
    response = await client.post(
        "/api/notifications/tick", params={"at": at.isoformat()}, headers=_auth(admin_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def inbox(client, user_id: int) -> dict:
    response = await client.get(f"/api/notifications/{user_id}", headers=_auth(user_id))
    assert response.status_code == 200, response.text
    return response.json()


async def deliveries(factory, user_id: int) -> list[ReminderDelivery]:
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(ReminderDelivery)
                    .where(ReminderDelivery.user_id == user_id)
                    .order_by(ReminderDelivery.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


def kinds(page: dict) -> list[str]:
    return [item["rule_code"] for item in page["items"]]


@pytest.mark.asyncio
async def test_daily_training_reminder_has_focus_and_duration(client, session_factory):
    """AC1：训练日未打卡 → 一条每日训练提醒，正文含重点与时长，带可跳转目标。"""
    user = await seed_user(session_factory, openid="ac1-owner")
    await seed_plan(session_factory, user.id)
    admin = await seed_user(session_factory, openid="ac1-admin", admin=True)

    await run_tick(client, admin.id, WEDNESDAY)

    page = await inbox(client, user.id)
    assert kinds(page) == ["daily_training"]
    item = page["items"][0]
    assert "胸背" in item["body"]
    assert "45 分钟" in item["body"]
    assert item["target_path"] == "/"


@pytest.mark.asyncio
async def test_checked_in_day_suppresses_daily_training(client, session_factory):
    """AC1 对照：当天已打卡 → 不再产生每日训练提醒。"""
    user = await seed_user(session_factory, openid="ac1-checked")
    await seed_plan(session_factory, user.id)
    await seed_checkins(session_factory, user.id, [TODAY])
    admin = await seed_user(session_factory, openid="ac1-admin-2", admin=True)

    await run_tick(client, admin.id, WEDNESDAY)

    assert "daily_training" not in kinds(await inbox(client, user.id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("days_since", "expected"),
    [
        (3, True),
        (4, False),
        (6, False),
        (7, True),
        (13, False),
        (14, True),
        (21, True),
        (15, False),
    ],
)
async def test_recall_ladder(client, session_factory, days_since, expected):
    """AC2：3/7/14 天阶梯；6 天不发；14 天起每 7 天一次。"""
    openid = f"ac2-{days_since}"
    user = await seed_user(session_factory, openid=openid)
    # 今天设为休息日，隔离出召回规则（每日训练属于 AC1）。
    await seed_plan(session_factory, user.id, rest_days={TODAY.isoweekday()})
    await seed_checkins(
        session_factory, user.id, [TODAY - datetime.timedelta(days=days_since)]
    )
    admin = await seed_user(session_factory, openid=f"ac2-admin-{days_since}", admin=True)

    await run_tick(client, admin.id, WEDNESDAY)

    page = await inbox(client, user.id)
    delivered_recall = [item for item in page["items"] if item["rule_code"] == "recall_inactive"]
    assert bool(delivered_recall) is expected
    if expected:
        assert str(days_since) in delivered_recall[0]["title"]


@pytest.mark.asyncio
async def test_recall_fires_even_when_reminded_on_other_days(client, session_factory):
    """AC2 回归：之前几天收到过提醒，不应让 3/7/14 天阶梯失效（防「叠加」误伤）。"""
    user = await seed_user(session_factory, openid="ac2-history")
    await seed_plan(session_factory, user.id, rest_days={TODAY.isoweekday()})
    await seed_checkins(
        session_factory, user.id, [TODAY - datetime.timedelta(days=3)]
    )
    await seed_delivery(
        session_factory,
        user.id,
        rule_code='daily_training',
        local_date=TODAY - datetime.timedelta(days=1),
    )
    admin = await seed_user(session_factory, openid='ac2-history-admin', admin=True)

    await run_tick(client, admin.id, WEDNESDAY)

    page = await inbox(client, user.id)
    assert 'recall_inactive' in kinds(page)


@pytest.mark.asyncio
async def test_weekly_goal_hit_once_per_week(client, session_factory):
    """AC3：本周达成目标当天发一条，同周期内重复 tick / 次日都不再发。"""
    user = await seed_user(session_factory, openid="ac3-hit")
    await seed_plan(session_factory, user.id)
    await seed_checkins(
        session_factory,
        user.id,
        [WEEK_START, WEEK_START + datetime.timedelta(days=1), TODAY],
    )
    admin = await seed_user(session_factory, openid="ac3-admin", admin=True)

    await run_tick(client, admin.id, WEDNESDAY)
    page = await inbox(client, user.id)
    assert "weekly_goal_hit" in kinds(page)

    await run_tick(client, admin.id, THURSDAY)
    again = await inbox(client, user.id)
    assert kinds(again).count("weekly_goal_hit") == 1

    rows = await deliveries(session_factory, user.id)
    weekly = [row for row in rows if row.rule_code == "weekly_goal_hit"]
    assert any(
        row.status == "skipped"
        and row.payload.get("skip_reason") == "already_sent_this_week"
        for row in weekly
    )


@pytest.mark.asyncio
async def test_weekly_goal_gap_on_week_end(client, session_factory):
    """AC3：周期末仍有缺口 → 一条含「还差几次」的提醒。"""
    user = await seed_user(session_factory, openid="ac3-gap")
    await seed_plan(session_factory, user.id)
    await seed_checkins(session_factory, user.id, [WEEK_START])
    admin = await seed_user(session_factory, openid="ac3-admin-2", admin=True)

    await run_tick(client, admin.id, SUNDAY)

    page = await inbox(client, user.id)
    gap = [item for item in page["items"] if item["rule_code"] == "weekly_goal_gap"]
    assert gap, kinds(page)
    assert "还差 2 次" in gap[0]["body"]


@pytest.mark.asyncio
async def test_quiet_hours_defers_inside_window_and_skips_after(client, session_factory):
    """AC4：区间内且窗口还开着 → 顺延（本轮不落记录）；窗口已过 → 记跳过不跨日补发。"""
    user = await seed_user(session_factory, openid="ac4-defer")
    await seed_plan(session_factory, user.id)
    await seed_preferences(
        session_factory, user.id, quiet_hours_start="19:30", quiet_hours_end="20:00"
    )
    admin = await seed_user(session_factory, openid="ac4-admin", admin=True)

    await run_tick(client, admin.id, WEDNESDAY.replace(hour=19, minute=45))
    assert await deliveries(session_factory, user.id) == []

    await run_tick(client, admin.id, WEDNESDAY.replace(hour=20, minute=5))
    assert "daily_training" in kinds(await inbox(client, user.id))

    # 窗口已过：22:30 在免打扰（22:00–08:00）内，且免打扰结束已超出当日窗口 23:00 之前？
    # 结束在次日 08:00 > 窗口结束 23:00，因此直接记跳过。
    late = await seed_user(session_factory, openid="ac4-late")
    await seed_plan(session_factory, late.id)
    await run_tick(client, admin.id, WEDNESDAY.replace(hour=22, minute=30))
    rows = await deliveries(session_factory, late.id)
    assert rows and all(row.status == "skipped" for row in rows)
    assert rows[0].payload.get("skip_reason") == "quiet_hours"
    assert (await inbox(client, late.id))["total"] == 0


@pytest.mark.asyncio
async def test_after_window_is_skipped_and_not_resent_later(client, session_factory):
    """AC4：窗口关闭后（23:30）的候选记 outside_daily_window 跳过，不跨日补发。"""
    user = await seed_user(session_factory, openid='ac4-after')
    await seed_plan(session_factory, user.id)
    admin = await seed_user(session_factory, openid='ac4-after-admin', admin=True)

    await run_tick(client, admin.id, WEDNESDAY.replace(hour=23, minute=30))

    assert (await inbox(client, user.id))['total'] == 0
    response = await client.get(
        f'/api/notifications/deliveries?user_id={user.id}&status=skipped',
        headers=_auth(admin.id),
    )
    reasons = [item['skip_reason'] for item in response.json()['items']]
    assert 'outside_daily_window' in reasons


@pytest.mark.asyncio
async def test_daily_cap_keeps_priority_order_and_records_skips(client, session_factory):
    """AC5：同日三条候选、上限 2 → 用户看到 2 条，被裁的留下 daily_cap 跳过记录。"""
    user = await seed_user(session_factory, openid="ac5-owner", has_analysis=False)
    await seed_plan(session_factory, user.id)
    await seed_checkins(
        session_factory, user.id, [TODAY - datetime.timedelta(days=3)]
    )
    admin = await seed_user(session_factory, openid="ac5-admin", admin=True)
    await seed_preferences(session_factory, user.id, daily_cap=2)

    summary = await run_tick(client, admin.id, WEDNESDAY)

    page = await inbox(client, user.id)
    assert page["total"] == 2
    # 召回 > 每日训练 > 引导：被裁掉的必然是优先级最低的引导提醒。
    assert "onboarding_nudge" not in kinds(page)
    assert summary["skipped"] >= 1

    rows = await deliveries(session_factory, user.id)
    capped = [
        row
        for row in rows
        if row.status == "skipped" and row.payload.get("skip_reason") == "daily_cap"
    ]
    assert capped and capped[0].rule_code == "onboarding_nudge"


@pytest.mark.asyncio
async def test_preferences_defaults_toggle_and_rejection(client, session_factory):
    """AC6：默认值、逐类开关生效、非法偏好 422 且已存偏好不变。"""
    user = await seed_user(session_factory, openid="ac6-owner")
    await seed_plan(session_factory, user.id)

    defaults = await client.get(
        f"/api/notifications/{user.id}/preferences", headers=_auth(user.id)
    )
    assert defaults.status_code == 200
    body = defaults.json()
    assert body["daily_training_enabled"] is True
    assert body["rest_day_note_enabled"] is False
    assert body["daily_cap"] == 2
    assert body["quiet_hours_start"] == "22:00"

    disabled = {**body, "daily_training_enabled": False}
    updated = await client.put(
        f"/api/notifications/{user.id}/preferences", json=disabled, headers=_auth(user.id)
    )
    assert updated.status_code == 200
    assert updated.json()["daily_training_enabled"] is False

    await seed_checkins(
        session_factory, user.id, [TODAY - datetime.timedelta(days=3)]
    )
    admin = await seed_user(session_factory, openid="ac6-admin", admin=True)
    await run_tick(client, admin.id, WEDNESDAY)
    after_tick = kinds(await inbox(client, user.id))
    assert "daily_training" not in after_tick
    assert "recall_inactive" in after_tick  # 其他类不受影响

    invalid_same_hours = {**disabled, "quiet_hours_start": "21:00", "quiet_hours_end": "21:00"}
    rejected = await client.put(
        f"/api/notifications/{user.id}/preferences",
        json=invalid_same_hours,
        headers=_auth(user.id),
    )
    assert rejected.status_code == 422

    invalid_cap = {**disabled, "daily_cap": 9}
    rejected_cap = await client.put(
        f"/api/notifications/{user.id}/preferences",
        json=invalid_cap,
        headers=_auth(user.id),
    )
    assert rejected_cap.status_code == 422

    after = await client.get(
        f"/api/notifications/{user.id}/preferences", headers=_auth(user.id)
    )
    assert after.json()["daily_training_enabled"] is False
    assert after.json()["daily_cap"] == 2


@pytest.mark.asyncio
async def test_skipped_candidates_are_queryable_by_ops(client, session_factory):
    """AC5 的可查询性：被裁掉的候选能通过内部接口按用户/状态查到，并带原因。"""
    user = await seed_user(session_factory, openid="ac5-query", has_analysis=False)
    await seed_plan(session_factory, user.id)
    await seed_checkins(session_factory, user.id, [TODAY - datetime.timedelta(days=3)])
    admin = await seed_user(session_factory, openid="ac5-query-admin", admin=True)
    await seed_preferences(session_factory, user.id, daily_cap=2)
    await run_tick(client, admin.id, WEDNESDAY)

    response = await client.get(
        f"/api/notifications/deliveries?user_id={user.id}&status=skipped",
        headers=_auth(admin.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert all(item["status"] == "skipped" for item in body["items"])
    assert any(item["skip_reason"] == "daily_cap" for item in body["items"])

    forbidden = await client.get(
        f"/api/notifications/deliveries?user_id={user.id}", headers=_auth(user.id)
    )
    assert forbidden.status_code == 403
