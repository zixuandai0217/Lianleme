"""调整结论落盘契约（工单 08）的外部行为测试。

打卡触发调整后，「往哪个方向动、为什么」必须能独立于页面被读出来；
无记录与「方向 keep」必须是两种可区分的状态；同一计划多次调整不能互相覆盖；
调整失败不影响打卡事实，并以稳定错误码可观测。
"""

import datetime
import json
import logging
import types
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.plan.plan_service as plan_service_module
import app.services.workout.workout_service as workout_service_module
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.logging import StructuredJsonFormatter
from app.main import app
from app.models.plan import TrainingPlan
from app.models.user import User
from app.services.ai.adjust_analyzers import (
    COMPLETENESS_DEFAULT,
    analyze_completion,
    analyze_fatigue,
    analyze_sleep,
)
from app.services.ai.adjust_merge import (
    build_reason,
    decide_direction,
    delta_percent_for,
    merge_results,
)

TODAY = datetime.date.today()


def week_plan() -> list[dict]:
    """每天一个动作的简单计划，足够让调整有对象。"""
    return [
        {
            "day": weekday,
            "focus": "全身",
            "exercises": [
                {
                    "name": "深蹲",
                    "sets": 3,
                    "reps": "12",
                    "weight_suggestion": "自重",
                    "tips": "挺胸收腹",
                    "rest_seconds": 60,
                }
            ],
            "estimated_duration": 30,
            "is_rest_day": False,
        }
        for weekday in range(1, 8)
    ]


class _FakeAdjuster:
    """复刻 AdjustGraph 的出口（方向 + 理由），用生产规则而不是另写一套阈值。

    早先这里手抄了一份「0.8 加量 / 0.5 减量」的路由，工单 24 改成五维合并后两份策略
    会互相矛盾；现在直接调用生产分析器与合并函数，替身只负责「不调模型」。
    """

    def __init__(self, user_id: int, db=None):
        self.user_id = user_id
        self.db = db

    async def run(
        self, completion_rate: float, difficulty_rating: float, current_plan: dict
    ) -> dict:
        dimensions = [
            analyze_completion({"completion_rates": [completion_rate]}),
            analyze_fatigue({}),
            analyze_sleep({}),
        ]
        merged = merge_results(dimensions, completion_rate=completion_rate)
        participating = any(
            entry.data_completeness != COMPLETENESS_DEFAULT for entry in dimensions
        )
        direction = decide_direction(
            merged.overall_score, completion_rate, participating=participating
        )
        return {
            "user_id": self.user_id,
            "completion_rate": completion_rate,
            "difficulty_rating": difficulty_rating,
            "current_plan": current_plan,
            "adjustment_type": direction,
            "adjusted_plan": current_plan,
            "reason": build_reason(
                merged, direction, completion_rate, participating=participating
            ),
            "dimensions": [entry.to_dict() for entry in dimensions],
            "merged": merged.to_dict(),
            "delta_percent": delta_percent_for(direction),
        }


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    db_path = tmp_path / "adjustments.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="adj-owner", nickname="Owner")
        other = User(openid="adj-other", nickname="Other")
        session.add_all([owner, other])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(other)
        return {"owner": owner, "other": other}


@pytest_asyncio.fixture
async def active_plan(session_factory, users):
    async with session_factory() as session:
        plan = TrainingPlan(
            user_id=users["owner"].id,
            week_start=TODAY,
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
def background_tasks(monkeypatch, session_factory):
    """捕获打卡后调度的调整协程，让测试可以确定性地执行它。"""
    captured: list = []

    def _capture(coroutine):
        captured.append(coroutine)
        return types.SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        workout_service_module, "asyncio", types.SimpleNamespace(create_task=_capture)
    )
    monkeypatch.setattr(workout_service_module, "AsyncSessionLocal", session_factory)
    return captured


@pytest.fixture(autouse=True)
def fake_adjuster(monkeypatch):
    monkeypatch.setattr(plan_service_module, "AdjustGraph", _FakeAdjuster)


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


async def check_in(client, user_id: int, *, completed: int, total: int):
    """提交一次打卡；返回响应，由调用方断言状态码。"""
    return await client.post(
        "/api/workout/complete",
        json={
            "user_id": user_id,
            "workout_date": TODAY.isoformat(),
            "total_sets": total,
            "completed_sets": completed,
            "duration_minutes": 30,
            "difficulty_rating": 3,
        },
        headers=_auth(user_id),
    )


async def latest_outcome(client, user_id: int) -> dict:
    response = await client.get(
        f"/api/plan/{user_id}/adjustments/latest", headers=_auth(user_id)
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_checkin_persists_readable_adjustment_outcome(
    client, users, active_plan, background_tasks, session_factory
):
    """AC1：打卡触发调整后可读到方向、含触发数值的理由、完成率、时间与计划标识。"""
    response = await check_in(client, users["owner"].id, completed=9, total=10)
    assert response.status_code == 200
    assert background_tasks, "打卡后应调度一次调整"
    await background_tasks[0]

    body = await latest_outcome(client, users["owner"].id)
    outcome = body["outcome"]
    assert outcome is not None
    assert outcome["direction"] == "increase"
    assert outcome["completion_rate"] == pytest.approx(0.9)
    assert outcome["plan_id"] == active_plan.id
    assert "90%" in outcome["reason"]
    assert outcome["adjustment_id"].startswith("adj_")
    assert outcome["created_at"]


@pytest.mark.asyncio
async def test_plan_row_references_the_latest_outcome(
    client, users, active_plan, background_tasks, session_factory
):
    """存储不变量（非路由契约）：计划侧只存引用，指向的正是落盘的那条结论。"""
    await check_in(client, users["owner"].id, completed=9, total=10)
    await background_tasks[0]
    outcome = (await latest_outcome(client, users["owner"].id))["outcome"]

    async with session_factory() as session:
        plan = await session.get(TrainingPlan, active_plan.id)
        assert plan.latest_adjustment_id == outcome["adjustment_id"]


@pytest.mark.asyncio
async def test_no_adjustment_is_an_explicit_empty_state_not_keep(client, users, active_plan):
    """AC2：没有调整记录时返回 outcome=null，与「方向 keep」可区分，且不是 404。"""
    empty = await latest_outcome(client, users["owner"].id)
    assert empty == {"outcome": None}


@pytest.mark.asyncio
async def test_keep_direction_is_a_real_record(
    client, users, active_plan, background_tasks
):
    """AC2 对照：方向为 keep 时 outcome 非空，不能被当成「没有调整」。"""
    response = await check_in(client, users["owner"].id, completed=6, total=10)
    assert response.status_code == 200
    await background_tasks[0]

    outcome = (await latest_outcome(client, users["owner"].id))["outcome"]
    assert outcome is not None
    assert outcome["direction"] == "keep"


@pytest.mark.asyncio
async def test_multiple_adjustments_on_one_plan_stay_addressable(
    client, users, active_plan, background_tasks
):
    """AC3：同一计划调整两次，latest 指向本次，旧结论仍可按标识取到。"""
    await check_in(client, users["owner"].id, completed=9, total=10)
    await background_tasks[0]
    first = (await latest_outcome(client, users["owner"].id))["outcome"]

    await check_in(client, users["owner"].id, completed=2, total=10)
    await background_tasks[1]
    second = (await latest_outcome(client, users["owner"].id))["outcome"]

    assert first["adjustment_id"] != second["adjustment_id"]
    assert first["direction"] == "increase"
    assert second["direction"] == "decrease"
    assert first["plan_id"] == second["plan_id"] == active_plan.id

    first_again = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/{first['adjustment_id']}",
        headers=_auth(users["owner"].id),
    )
    assert first_again.status_code == 200
    assert first_again.json()["direction"] == "increase"


@pytest.mark.asyncio
async def test_persist_failure_keeps_checkin_and_is_observable(
    client, users, active_plan, background_tasks, monkeypatch, caplog
):
    """AC4：结论写入失败时打卡仍成功、记录可见，失败以稳定分类记日志。"""

    async def _boom(self, **kwargs):
        raise RuntimeError("adjustment store is down")

    monkeypatch.setattr(
        plan_service_module.PlanService, "adjust_plan_after_workout", _boom
    )

    response = await check_in(client, users["owner"].id, completed=8, total=10)
    assert response.status_code == 200
    await background_tasks[0]

    stats = await client.get(
        f"/api/workout/{users['owner'].id}/stats", headers=_auth(users["owner"].id)
    )
    assert stats.status_code == 200
    assert stats.json()["total_checkins"] == 1

    failures = [
        payload
        for payload in _payloads(caplog)
        if payload.get("event") == "plan.adjustment.failed"
    ]
    assert failures, "调整失败必须留下可观测事件"
    event = failures[-1]
    assert event["error_code"] == "adjustment_persist_failed"
    assert event["level"] == "warning"
    assert event["user_id"] == users["owner"].id

    # 失败之后读取仍是显式空态，不会伪造一条结论。
    assert (await latest_outcome(client, users["owner"].id))["outcome"] is None


@pytest.mark.asyncio
async def test_reading_another_users_adjustment_is_forbidden(
    client, users, active_plan, background_tasks
):
    """权限：调整结论只对本人可见。"""
    await check_in(client, users["owner"].id, completed=8, total=10)
    await background_tasks[0]
    outcome = (await latest_outcome(client, users["owner"].id))["outcome"]

    latest = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/latest",
        headers=_auth(users["other"].id),
    )
    assert latest.status_code == 403

    single = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/{outcome['adjustment_id']}",
        headers=_auth(users["other"].id),
    )
    assert single.status_code == 403


@pytest.mark.asyncio
async def test_unknown_adjustment_id_is_a_clean_404(client, users, active_plan):
    response = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/adj_missing",
        headers=_auth(users["owner"].id),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "adjustment_not_found"
