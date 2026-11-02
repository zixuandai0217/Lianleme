"""训练会话推进 / 恢复 / 权限（工单 22）的路由层行为测试。

会话的本质是「一串 HTTP 请求 → 可观察的进度与指针」，因此全部断言都落在响应上；
只有「同一天只有一条会话」这类存储不变量直接查一次行数。
"""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.plan import TrainingPlan
from app.models.user import User
from app.models.workout_session import WorkoutSession

TZ = ZoneInfo("Asia/Shanghai")
TODAY = datetime.date(2026, 3, 18)  # 周三
WEEK_START = TODAY - datetime.timedelta(days=TODAY.weekday())


def week_plan(rest_days: set[int] | None = None) -> list[dict]:
    rest_days = rest_days or set()
    days = []
    for weekday in range(1, 8):
        is_rest = weekday in rest_days
        days.append(
            {
                "day": weekday,
                "focus": "胸背",
                "exercises": []
                if is_rest
                else [
                    {
                        "name": "卧推",
                        "sets": 4,
                        "reps": "8-12",
                        "weight_suggestion": "体重 40%",
                        "tips": "肩胛收紧",
                        "rest_seconds": 90,
                    },
                    {
                        "name": "划船",
                        "sets": 3,
                        "reps": "10-12",
                        "weight_suggestion": "体重 30%",
                        "tips": "背部发力",
                        "rest_seconds": 75,
                    },
                ],
                "estimated_duration": 0 if is_rest else 45,
                "is_rest_day": is_rest,
            }
        )
    return days


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    db_path = tmp_path / "workout-sessions.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="session-owner", nickname="Owner")
        other = User(openid="session-other", nickname="Other")
        session.add_all([owner, other])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(other)
        return {"owner": owner, "other": other}


@pytest_asyncio.fixture
async def training_plan(session_factory, users):
    async with session_factory() as session:
        plan = TrainingPlan(
            user_id=users["owner"].id,
            week_start=WEEK_START,
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
def frozen_today(monkeypatch):
    from app.services.workout.session_service import WorkoutSessionService

    monkeypatch.setattr(WorkoutSessionService, "_today", staticmethod(lambda: TODAY))


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def start(client, user_id: int) -> dict:
    response = await client.post(
        "/api/workout/sessions/start", json={"user_id": user_id}, headers=_auth(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def read(client, user_id: int, session_id: str) -> dict:
    response = await client.get(
        f"/api/workout/sessions/{session_id}", headers=_auth(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def complete_set(client, user_id: int, session_id: str, exercise: int, set_index: int):
    return await client.post(
        f"/api/workout/sessions/{session_id}/sets",
        json={"exercise_index": exercise, "set_index": set_index},
        headers=_auth(user_id),
    )


async def skip(client, user_id: int, session_id: str, exercise: int, reason: str):
    return await client.post(
        f"/api/workout/sessions/{session_id}/skip",
        json={"exercise_index": exercise, "reason": reason},
        headers=_auth(user_id),
    )


async def session_rows(factory, user_id: int) -> int:
    async with factory() as session:
        return (
            await session.execute(
                select(func.count(WorkoutSession.id)).where(WorkoutSession.user_id == user_id)
            )
        ).scalar() or 0


@pytest.mark.asyncio
async def test_start_creates_one_session_with_first_exercise(
    client, users, training_plan, session_factory
):
    """AC1：开始训练返回进行中会话、第一个动作与总组数；同日重复开始返回同一个会话。"""
    first = await start(client, users["owner"].id)

    assert first["status"] == "in_progress"
    assert first["session_id"].startswith("ws_")
    assert first["progress"]["total_sets"] == 7
    assert first["progress"]["completed_sets"] == 0
    assert first["current_exercise"]["name"] == "卧推"
    assert first["current_exercise"]["sets"] == 4
    assert first["can_checkin"] is False

    second = await start(client, users["owner"].id)
    assert second["session_id"] == first["session_id"]
    assert await session_rows(session_factory, users["owner"].id) == 1


@pytest.mark.asyncio
async def test_complete_set_advances_progress_and_is_idempotent(
    client, users, training_plan
):
    """AC2：完成一组推进指针；重复提交同一组不重复计数、不回退。"""
    session = await start(client, users["owner"].id)
    session_id = session["session_id"]

    response = await complete_set(client, users["owner"].id, session_id, 0, 0)
    assert response.status_code == 200
    body = response.json()
    assert body["progress"]["completed_sets"] == 1
    assert body["current_exercise"]["completed_sets"] == 1
    assert body["current_exercise"]["name"] == "卧推"

    duplicate = await complete_set(client, users["owner"].id, session_id, 0, 0)
    assert duplicate.status_code == 200
    assert duplicate.json()["progress"]["completed_sets"] == 1

    body = (await complete_set(client, users["owner"].id, session_id, 0, 1)).json()
    assert body["progress"]["completed_sets"] == 2
    assert body["current_exercise"]["target_set_number"] == 3


@pytest.mark.asyncio
async def test_skip_exercise_records_reason_without_adding_sets(
    client, users, training_plan
):
    """AC3：跳过必须带原因，动作留在明细里但不计入完成组数。"""
    session = await start(client, users["owner"].id)
    session_id = session["session_id"]
    await complete_set(client, users["owner"].id, session_id, 0, 0)

    missing_reason = await client.post(
        f"/api/workout/sessions/{session_id}/skip",
        json={"exercise_index": 1},
        headers=_auth(users["owner"].id),
    )
    assert missing_reason.status_code == 422

    response = await skip(client, users["owner"].id, session_id, 1, "器械被占")
    assert response.status_code == 200
    body = response.json()
    assert body["progress"]["completed_sets"] == 1
    skipped = next(item for item in body["exercises"] if item["index"] == 1)
    assert skipped["skipped"] is True
    assert skipped["skip_reason"] == "器械被占"
    assert skipped["status"] == "skipped"


@pytest.mark.asyncio
async def test_session_resumes_from_database(client, users, training_plan):
    """AC4：重新读取（进程内存清空）后进度与可打卡状态一致。"""
    session = await start(client, users["owner"].id)
    session_id = session["session_id"]
    await complete_set(client, users["owner"].id, session_id, 0, 0)
    await complete_set(client, users["owner"].id, session_id, 0, 1)
    before = await read(client, users["owner"].id, session_id)

    after = await read(client, users["owner"].id, session_id)
    assert after["progress"] == before["progress"]
    assert after["current_exercise"]["name"] == before["current_exercise"]["name"]
    assert after["can_checkin"] == before["can_checkin"]
    assert after["session_date"] == TODAY.isoformat()


@pytest.mark.asyncio
async def test_finishing_all_exercises_enables_checkin(client, users, training_plan):
    """全部动作完成或跳过后 can_checkin 才为真（供收尾打卡入口判断）。"""
    session = await start(client, users["owner"].id)
    session_id = session["session_id"]

    for set_index in range(4):
        await complete_set(client, users["owner"].id, session_id, 0, set_index)
    assert (await read(client, users["owner"].id, session_id))["can_checkin"] is False

    response = await skip(client, users["owner"].id, session_id, 1, "时间不够")
    body = response.json()
    assert body["can_checkin"] is True
    assert body["finished"] is True
    assert body["current_exercise"] is None


@pytest.mark.asyncio
async def test_permissions_and_empty_states(client, users, training_plan, session_factory):
    """AC5：越权 403、未登录 401；休息日 / 无计划返回稳定错误码且不建会话。"""
    session = await start(client, users["owner"].id)
    session_id = session["session_id"]

    other_read = await client.get(
        f"/api/workout/sessions/{session_id}", headers=_auth(users["other"].id)
    )
    assert other_read.status_code == 403
    anonymous = await client.get(f"/api/workout/sessions/{session_id}")
    assert anonymous.status_code == 401
    forbidden_start = await client.post(
        "/api/workout/sessions/start", json={"user_id": users["owner"].id}
    )
    assert forbidden_start.status_code == 401

    # 休息日：单独一个用户，当天计划是休息 -> 409 + rest_day，且不建会话
    async with session_factory() as db:
        rest_user = User(openid="session-rest", nickname="Rest")
        noplan_user = User(openid="session-noplan", nickname="NoPlan")
        db.add_all([rest_user, noplan_user])
        await db.commit()
        await db.refresh(rest_user)
        await db.refresh(noplan_user)
        db.add(
            TrainingPlan(
                user_id=rest_user.id,
                week_start=WEEK_START,
                weekly_plan=week_plan({TODAY.isoweekday()}),
                difficulty_factor=1.0,
                status="active",
            )
        )
        await db.commit()

    rest = await client.post(
        "/api/workout/sessions/start",
        json={"user_id": rest_user.id},
        headers=_auth(rest_user.id),
    )
    assert rest.status_code == 409
    assert rest.json()["detail"]["code"] == "rest_day"
    assert await session_rows(session_factory, rest_user.id) == 0

    # 无计划用户 -> 409 + no_plan，且没有产生会话
    no_plan = await client.post(
        "/api/workout/sessions/start",
        json={"user_id": noplan_user.id},
        headers=_auth(noplan_user.id),
    )
    assert no_plan.status_code == 409
    assert no_plan.json()["detail"]["code"] == "no_plan"
    assert await session_rows(session_factory, noplan_user.id) == 0


async def seed_session(
    factory,
    user_id: int,
    *,
    session_date: datetime.date,
    started_at: datetime.datetime,
    last_activity_at: datetime.datetime,
    completed_sets: int = 2,
    status: str = "in_progress",
) -> str:
    """Seed a session row directly (simulates one written before a process restart)."""
    exercises = [
        {
            "order": 1,
            "name": "卧推",
            "sets": 4,
            "reps": "8-12",
            "weight_suggestion": "体重 40%",
            "tips": "肩胛收紧",
            "rest_seconds": 90,
            "completed_sets": completed_sets,
            "skipped": False,
            "skip_reason": None,
        },
        {
            "order": 2,
            "name": "划船",
            "sets": 3,
            "reps": "10-12",
            "weight_suggestion": "体重 30%",
            "tips": "背部发力",
            "rest_seconds": 75,
            "completed_sets": 0,
            "skipped": False,
            "skip_reason": None,
        },
    ]
    session_id = f"ws_seed_{user_id}_{session_date.isoformat()}"
    async with factory() as db:
        db.add(
            WorkoutSession(
                id=session_id,
                user_id=user_id,
                plan_id=None,
                session_date=session_date,
                status=status,
                total_sets=7,
                completed_sets=completed_sets,
                exercises=exercises,
                started_at=started_at,
                last_activity_at=last_activity_at,
            )
        )
        await db.commit()
    return session_id


@pytest.mark.asyncio
async def test_blank_skip_reason_is_rejected(client, users, training_plan):
    """AC3：纯空白的「原因」不算带原因，不能写进明细。"""
    session = await start(client, users["owner"].id)
    response = await client.post(
        f"/api/workout/sessions/{session['session_id']}/skip",
        json={"exercise_index": 1, "reason": "   "},
        headers=_auth(users["owner"].id),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cross_midnight_session_is_resumed_by_current_session(
    client, users, training_plan, session_factory
):
    """AC4：跨零点继续训练仍归属开始当天，且页面用的 current 接口能恢复它。"""
    yesterday = TODAY - datetime.timedelta(days=1)
    wall_clock = datetime.datetime.now(datetime.timezone.utc)
    session_id = await seed_session(
        session_factory,
        users["owner"].id,
        session_date=yesterday,
        started_at=wall_clock - datetime.timedelta(hours=5),
        last_activity_at=wall_clock - datetime.timedelta(hours=2),
        completed_sets=3,
    )

    response = await client.get(
        f"/api/workout/sessions/current?user_id={users['owner'].id}",
        headers=_auth(users["owner"].id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["session_date"] == yesterday.isoformat()
    assert body["progress"]["completed_sets"] == 3

    # 再次点「开始训练」必须恢复同一个会话，而不是开一条新的。
    resumed = await client.post(
        "/api/workout/sessions/start",
        json={"user_id": users["owner"].id},
        headers=_auth(users["owner"].id),
    )
    assert resumed.status_code == 200
    assert resumed.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_idle_session_is_converged_to_abandoned(
    client, users, training_plan, session_factory
):
    """状态机：12 小时无活动的进行中会话在读取时收敛为 abandoned（只读）。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    session_id = await seed_session(
        session_factory,
        users["owner"].id,
        session_date=TODAY,
        started_at=now - datetime.timedelta(hours=14),
        last_activity_at=now - datetime.timedelta(hours=13),
    )

    response = await client.get(
        f"/api/workout/sessions/{session_id}", headers=_auth(users["owner"].id)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"

    current = await client.get(
        f"/api/workout/sessions/current?user_id={users['owner'].id}",
        headers=_auth(users["owner"].id),
    )
    assert current.status_code == 200
    assert current.json()["status"] == "abandoned"
    assert current.json()["can_checkin"] is False
