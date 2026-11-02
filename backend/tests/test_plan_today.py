"""今日训练三态契约（工单 07）的外部行为测试。

今日接口必须能区分「训练日 / 休息日 / 无计划」：首页据此渲染不同文案，
训练会话页与首用引导也依赖这个判定。三态都在路由层断言，不测服务内部实现。
"""

import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.plan import TrainingPlan
from app.models.user import User
from app.services.plan.plan_service import PlanService

# 冻结「今天」：三态判定依赖周几，用真实时钟会让用例在跨零点/跨周时不稳定。
TODAY = datetime.date(2026, 3, 18)  # 周三
TODAY_WEEKDAY = TODAY.isoweekday()


def week_plan(rest_days: set[int]) -> list[dict]:
    """构造一份七天计划，只把 ``rest_days`` 里的周几标成休息日。"""
    days = []
    for weekday in range(1, 8):
        is_rest = weekday in rest_days
        days.append(
            {
                "day": weekday,
                "focus": "休息" if is_rest else "全身",
                "exercises": []
                if is_rest
                else [
                    {
                        "name": "深蹲",
                        "sets": 3,
                        "reps": "12",
                        "weight_suggestion": "自重",
                        "tips": "挺胸收腹",
                        "rest_seconds": 60,
                    },
                    {
                        "name": "俯卧撑",
                        "sets": 4,
                        "reps": "10",
                        "weight_suggestion": "自重",
                        "tips": "保持身体平直",
                        "rest_seconds": 90,
                    },
                ],
                "estimated_duration": 0 if is_rest else 45,
                "is_rest_day": is_rest,
            }
        )
    return days


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    """Freeze the service clock so the weekday three-state check is deterministic."""
    monkeypatch.setattr(PlanService, "_today", staticmethod(lambda: TODAY))


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """隔离的 SQLite 库，避免污染 dev.db。"""
    db_path = tmp_path / "plan-today.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    """一个计划所有者与一个无关用户。"""
    async with session_factory() as session:
        owner = User(openid="today-owner", nickname="Owner")
        other = User(openid="today-other", nickname="Other")
        session.add_all([owner, other])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(other)
        return {"owner": owner, "other": other}


@pytest_asyncio.fixture
async def client(session_factory):
    """以隔离库为后端的路由层客户端。"""

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


async def get_today(client, user_id: int, *, as_user: int | None = None):
    """以 ``as_user``（默认本人）的身份读今日接口。"""
    return await client.get(
        f"/api/plan/{user_id}/today", headers=_auth(as_user or user_id)
    )


async def seed_plan(factory, user_id: int, *, rest_days: set[int], status: str = "active") -> None:
    async with factory() as session:
        session.add(
            TrainingPlan(
                user_id=user_id,
                week_start=TODAY - datetime.timedelta(days=TODAY.weekday()),
                weekly_plan=week_plan(rest_days),
                difficulty_factor=1.0,
                status=status,
            )
        )
        await session.commit()


async def seed_plan_without_today(factory, user_id: int) -> None:
    """退化数据：计划存在，但当周计划里没有今天这一条。"""
    days = [day for day in week_plan(set()) if day["day"] != TODAY_WEEKDAY]
    async with factory() as session:
        session.add(
            TrainingPlan(
                user_id=user_id,
                week_start=TODAY,
                weekly_plan=days,
                difficulty_factor=1.0,
                status="active",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_training_day_returns_the_workout_with_counts(client, users, session_factory):
    """AC1：训练日返回动作清单，并带动作数、总组数与预计时长。"""
    await seed_plan(session_factory, users["owner"].id, rest_days=set())

    response = await get_today(client, users["owner"].id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "training_day"
    assert body["is_rest_day"] is False
    assert body["day"] == TODAY_WEEKDAY
    assert body["focus"] == "全身"
    assert body["estimated_duration"] == 45
    assert body["exercise_count"] == 2
    assert body["total_sets"] == 7
    assert [exercise["name"] for exercise in body["exercises"]] == ["深蹲", "俯卧撑"]


@pytest.mark.asyncio
async def test_rest_day_has_recovery_copy_and_no_exercise_list(client, users, session_factory):
    """AC2：休息日返回恢复文案，不返回动作清单。"""
    await seed_plan(session_factory, users["owner"].id, rest_days={TODAY_WEEKDAY})

    response = await get_today(client, users["owner"].id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rest_day"
    assert body["is_rest_day"] is True
    assert body["message"]
    assert not body.get("exercises")
    assert body.get("exercise_count") is None
    assert body.get("total_sets") is None


@pytest.mark.asyncio
async def test_no_plan_is_its_own_state_not_a_404_and_not_a_rest_day(client, users):
    """AC3：从未生成计划的用户拿到 200 + 无计划态，且不带休息日文案。"""
    response = await get_today(client, users["owner"].id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_plan"
    assert body["is_rest_day"] is False
    assert not body.get("exercises")
    assert not body.get("message")
    assert body.get("estimated_duration") is None


@pytest.mark.asyncio
async def test_archived_plan_is_no_plan(client, users, session_factory):
    """AC3：归档计划等于没有可用计划，不能伪装成休息日。"""
    await seed_plan(session_factory, users["owner"].id, rest_days=set(), status="archived")

    response = await get_today(client, users["owner"].id)

    assert response.status_code == 200
    assert response.json()["status"] == "no_plan"


@pytest.mark.asyncio
async def test_plan_missing_todays_entry_degrades_to_rest_not_a_broken_workout(
    client, users, session_factory
):
    """退化数据：计划存在但没有今天这一条时按休息日处理，绝不渲染成空训练日。"""
    await seed_plan_without_today(session_factory, users["owner"].id)

    response = await get_today(client, users["owner"].id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rest_day"
    assert not body.get("exercises")


@pytest.mark.asyncio
async def test_other_users_today_is_forbidden(client, users):
    """权限：只能读自己的今日安排。"""
    response = await get_today(client, users["other"].id, as_user=users["owner"].id)

    assert response.status_code == 403
