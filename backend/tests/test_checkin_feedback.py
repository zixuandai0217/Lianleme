"""打卡投递作业 + 四段式反馈（工单 28）的路由层契约。

打卡只负责写记录、投递一条持久作业并立刻返回；评估是否完成、是否失败都只影响
``feedback.plan_impact.status``，不影响打卡本身。四段反馈里的完成率由服务端按当日
会话明细计算，客户端自报数字不改变结果。
"""

from __future__ import annotations

import datetime
import types
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.workout.workout_service as workout_service_module
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.adjustment import PlanAdjustment
from app.models.adjustment_job import PlanAdjustmentJob
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.workout_session import WorkoutSession
from app.services.ai.llm_factory import LLMClientFactory
from app.services.plan.adjustment_job_service import AdjustmentJobService
from app.services.plan.plan_service import PlanService

TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)


def week_plan() -> list[dict]:
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


class _FakeLLM:
    """LLM 替身：只回一句固定建议，证明反馈来源标注为 model。"""

    def __init__(self, text: str = "模型建议：补够水，睡满七小时。"):
        self.text = text

    async def ainvoke(self, messages, **kwargs):
        return types.SimpleNamespace(content=self.text)


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    db_path = tmp_path / "checkin-feedback.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="feedback-owner", nickname="Owner")
        other = User(openid="feedback-other", nickname="Other")
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
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
def background_tasks(monkeypatch, session_factory):
    """捕获打卡后投递的评估协程：测试决定它何时执行，并断言没有同步调用。"""
    captured: list = []

    def _capture(coroutine):
        captured.append(coroutine)
        return types.SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        workout_service_module, "asyncio", types.SimpleNamespace(create_task=_capture)
    )
    monkeypatch.setattr(workout_service_module, "AsyncSessionLocal", session_factory)
    yield captured
    for coroutine in captured:
        coroutine.close()


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """默认所有用例都有可用模型；兜底路径在用例里单独把工厂打坏。"""

    async def fake_get_client(self, *args, **kwargs):
        return _FakeLLM()

    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)


@pytest.fixture
def adjustment_calls(monkeypatch):
    """记录评估是否真的被执行：打卡响应阶段必须为 0。"""
    calls: list = []
    original = PlanService.adjust_plan_after_workout

    async def wrapped(self, *args, **kwargs):
        calls.append((args, kwargs))
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(PlanService, "adjust_plan_after_workout", wrapped)
    return calls


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def check_in(
    client,
    user_id: int,
    *,
    completed: int = 9,
    total: int = 10,
    when: datetime.date = TODAY,
    duration: int = 30,
    difficulty: int = 3,
):
    return await client.post(
        "/api/workout/complete",
        json={
            "user_id": user_id,
            "workout_date": when.isoformat(),
            "total_sets": total,
            "completed_sets": completed,
            "duration_minutes": duration,
            "difficulty_rating": difficulty,
        },
        headers=_auth(user_id),
    )


async def seed_session(
    factory,
    user_id: int,
    *,
    session_date: datetime.date = TODAY,
    total: int = 10,
    completed: int = 6,
) -> str:
    """铺一条当日会话：两个动作、计划 10 组、实际完成 6 组。"""
    first_completed = min(completed, 4)
    second_completed = max(completed - 4, 0)
    exercises = [
        {
            "order": 1,
            "name": "深蹲",
            "sets": 6,
            "reps": "12",
            "weight_suggestion": "自重",
            "tips": "挺胸收腹",
            "rest_seconds": 60,
            "completed_sets": first_completed,
            "skipped": False,
            "skip_reason": None,
        },
        {
            "order": 2,
            "name": "划船",
            "sets": 4,
            "reps": "10",
            "weight_suggestion": "轻重量",
            "tips": "背部发力",
            "rest_seconds": 75,
            "completed_sets": second_completed,
            "skipped": False,
            "skip_reason": None,
        },
    ]
    session_id = f"ws_feedback_{user_id}_{session_date.isoformat()}"
    async with factory() as session:
        session.add(
            WorkoutSession(
                id=session_id,
                user_id=user_id,
                plan_id=None,
                session_date=session_date,
                status="in_progress",
                total_sets=total,
                completed_sets=completed,
                exercises=exercises,
            )
        )
        await session.commit()
    return session_id


async def seed_record(
    factory,
    user_id: int,
    *,
    when: datetime.date,
    completion_rate: float,
    total: int = 10,
    completed: int = 8,
) -> int:
    async with factory() as session:
        record = WorkoutRecord(
            user_id=user_id,
            workout_date=when,
            total_sets=total,
            completed_sets=completed,
            completion_rate=completion_rate,
            duration_minutes=25,
            difficulty_rating=3,
            ai_feedback="历史反馈",
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def row_count(factory, model) -> int:
    async with factory() as session:
        return int(
            await session.scalar(select(func.count()).select_from(model)) or 0
        )


async def current_plan(client, user_id: int) -> dict:
    response = await client.get(f"/api/plan/{user_id}/current", headers=_auth(user_id))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_checkin_returns_four_part_feedback_with_server_completion(
    client,
    users,
    active_plan,
    background_tasks,
    adjustment_calls,
    session_factory,
):
    """AC1/AC2：四段齐全；完成率来自会话明细而不是客户端自报；评估不阻塞。"""
    await seed_session(session_factory, users["owner"].id, total=10, completed=6)

    response = await check_in(client, users["owner"].id, completed=10, total=10)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completion_rate"] == pytest.approx(0.6)
    assert body["job_id"].startswith("job_")
    assert body["job_error"] is None

    feedback = body["feedback"]
    assert feedback["completion"] == {
        "completed_sets": 6,
        "total_sets": 10,
        "completion_rate": pytest.approx(0.6),
        "duration_minutes": 30,
    }
    assert feedback["comparison"]["has_previous"] is False
    assert feedback["comparison"]["previous_completion_rate"] is None
    assert feedback["comparison"]["delta_percent"] is None
    assert feedback["comparison"]["direction"] == "first_time"
    assert feedback["recovery"]["source"] == "model"
    assert feedback["recovery"]["tips"] == ["模型建议：补够水，睡满七小时。"]

    impact = feedback["plan_impact"]
    assert impact["status"] == "evaluating"
    assert impact["job_id"] == body["job_id"]
    assert impact["direction"] is None
    assert impact["before_summary"] is None
    assert impact["after_summary"] is None
    assert "评估" in impact["reason"]

    # 作业只是投递：响应阶段评估协程没有执行，作业仍停在 evaluating。
    assert adjustment_calls == []
    assert background_tasks, "打卡后应投递一次评估"
    async with session_factory() as session:
        job = await session.get(PlanAdjustmentJob, body["job_id"])
        assert job is not None and job.status == "evaluating"

    async with session_factory() as session:
        record = await session.get(WorkoutRecord, body["id"])
        assert record is not None
        assert record.completed_sets == 6
        assert record.total_sets == 10
        assert record.completion_rate == pytest.approx(0.6)
        assert record.adjustment_job_id == body["job_id"]
        assert record.plan_impact_status == "evaluating"
        session_row = await session.get(
            WorkoutSession, f"ws_feedback_{users['owner'].id}_{TODAY.isoformat()}"
        )
        assert session_row is not None and session_row.status == "completed"


@pytest.mark.asyncio
async def test_manual_fallback_uses_request_values_when_no_session(
    client, users, active_plan, background_tasks, session_factory
):
    """没有会话的旧提交路径保留：按请求值计算，但仅作为向后兼容。"""
    response = await check_in(client, users["owner"].id, completed=9, total=10)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completion_rate"] == pytest.approx(0.9)
    assert body["feedback"]["completion"]["completed_sets"] == 9
    assert body["feedback"]["completion"]["total_sets"] == 10
    assert await row_count(session_factory, WorkoutRecord) == 1


@pytest.mark.asyncio
async def test_recovery_falls_back_when_model_is_unavailable(
    client, users, active_plan, background_tasks, session_factory, monkeypatch
):
    """AC1：模型不可用时 tips 非空、标注 fallback，且打卡不 500。"""

    async def broken_get_client(self, *args, **kwargs):
        raise RuntimeError("model offline")

    monkeypatch.setattr(LLMClientFactory, "get_client", broken_get_client)

    response = await check_in(client, users["owner"].id, completed=4, total=10)

    assert response.status_code == 200, response.text
    feedback = response.json()["feedback"]
    assert feedback["recovery"]["source"] == "fallback"
    assert feedback["recovery"]["tips"], "兜底建议不允许为空"
    assert all(tip.strip() for tip in feedback["recovery"]["tips"])
    assert response.json()["ai_feedback"], "旧客户端依赖的 ai_feedback 仍然可读"


@pytest.mark.asyncio
async def test_evaluation_failure_only_changes_plan_impact_status(
    client, users, active_plan, background_tasks, monkeypatch, session_factory
):
    """AC2/AC6：评估失败仍 200；重复打卡复用同一条记录与同一个作业。"""
    await seed_session(session_factory, users["owner"].id, total=10, completed=6)

    async def _provider_boom(self, **kwargs):
        raise RuntimeError("provider timeout 504")

    monkeypatch.setattr(PlanService, "adjust_plan_after_workout", _provider_boom)

    first = await check_in(client, users["owner"].id)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["feedback"]["plan_impact"]["status"] == "evaluating"
    job_id = first_body["job_id"]

    await background_tasks[0]

    second = await check_in(client, users["owner"].id)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["id"] == first_body["id"]
    assert second_body["job_id"] == job_id
    assert second_body["feedback"]["plan_impact"]["status"] == "failed"
    assert second_body["feedback"]["completion"]["completion_rate"] == pytest.approx(0.6)
    assert second_body["feedback"]["comparison"]["has_previous"] is False
    assert second_body["feedback"]["recovery"]["tips"]

    assert await row_count(session_factory, WorkoutRecord) == 1
    assert await row_count(session_factory, PlanAdjustmentJob) == 1
    assert len(background_tasks) == 1, "重复打卡不能投递第二条作业"


@pytest.mark.asyncio
async def test_job_creation_failure_returns_200_with_not_dispatched(
    client, users, active_plan, background_tasks, monkeypatch, session_factory
):
    """AC2：作业投递失败时打卡成功，计划影响为「未投递」，其余三段完整。"""
    await seed_session(session_factory, users["owner"].id, total=10, completed=6)

    async def _boom(self, user_id):
        raise RuntimeError("job table unavailable")

    monkeypatch.setattr(AdjustmentJobService, "create_job", _boom)

    response = await check_in(client, users["owner"].id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] is None
    assert body["job_error"] == "job_not_created"
    impact = body["feedback"]["plan_impact"]
    assert impact["status"] == "not_dispatched"
    assert impact["job_id"] is None
    assert impact["direction"] is None
    assert impact["reason"]
    assert body["feedback"]["completion"]["completed_sets"] == 6
    assert body["feedback"]["comparison"]["has_previous"] is False
    assert body["feedback"]["recovery"]["tips"]
    assert background_tasks == []
    assert await row_count(session_factory, WorkoutRecord) == 1


@pytest.mark.asyncio
async def test_applied_projection_reads_the_same_adjustment_as_the_plan_card(
    client, users, active_plan, background_tasks, session_factory
):
    """AC3/AC4：方向、理由、前后摘要与计划解释卡同源；改结论两处同时变。"""
    first = await check_in(client, users["owner"].id, completed=9, total=10)
    assert first.status_code == 200, first.text
    job_id = first.json()["job_id"]
    await background_tasks[0]

    duplicate = await check_in(client, users["owner"].id, completed=9, total=10)
    assert duplicate.status_code == 200, duplicate.text
    feedback = duplicate.json()["feedback"]["plan_impact"]
    assert feedback["status"] == "applied"
    assert feedback["direction"] in ("increase", "decrease", "keep")
    assert feedback["reason"]
    assert feedback["before_summary"]
    assert feedback["after_summary"]

    explanation = (await current_plan(client, users["owner"].id))["explanation"][
        "latest_adjustment"
    ]
    assert explanation["direction"] == feedback["direction"]
    assert explanation["reason"] == feedback["reason"]
    # 前后摘要也必须逐字一致：两处都读同一个作业的计划差异快照。
    assert explanation["before_summary"] == feedback["before_summary"]
    assert explanation["after_summary"] == feedback["after_summary"]

    # 直接改「唯一存储」里的结论：两处投影必须同时变化，不需要第二次写入。
    async with session_factory() as session:
        job = await session.get(PlanAdjustmentJob, job_id)
        assert job is not None and job.adjustment_id
        adjustment = await session.get(PlanAdjustment, job.adjustment_id)
        assert adjustment is not None
        adjustment.reason = "手工改写后的唯一理由"
        adjustment.direction = "decrease"
        await session.commit()

    after_change = await check_in(client, users["owner"].id, completed=9, total=10)
    changed_feedback = after_change.json()["feedback"]["plan_impact"]
    assert changed_feedback["reason"] == "手工改写后的唯一理由"
    assert changed_feedback["direction"] == "decrease"

    changed_explanation = (await current_plan(client, users["owner"].id))["explanation"][
        "latest_adjustment"
    ]
    assert changed_explanation["reason"] == changed_feedback["reason"]
    assert changed_explanation["direction"] == changed_feedback["direction"]

    # 打卡记录侧没有第二份调整理由存储。
    assert "reason" not in WorkoutRecord.__table__.columns
    async with session_factory() as session:
        record = await session.get(WorkoutRecord, duplicate.json()["id"])
        assert record is not None
        assert record.adjustment_job_id == job_id
        assert record.plan_impact_status == "evaluating"


@pytest.mark.asyncio
async def test_pending_choice_is_not_applied_and_points_to_confirmation(
    client, users, active_plan, background_tasks, session_factory
):
    """AC4：停待确认时计划影响为 pending_choice，文案指向「等你确认」。"""
    first = await check_in(client, users["owner"].id, completed=9, total=10)
    job_id = first.json()["job_id"]

    async with session_factory() as session:
        job = await session.get(PlanAdjustmentJob, job_id)
        assert job is not None
        job.status = "pending_choice"
        job.adjustment_id = None
        job.plan_diff = None
        job.interrupt = {
            "reason_code": "injury_risk_high",
            "risk_level": "high",
            "options": [{"id": "reduce_intensity", "label": "降低强度", "recommended": True}],
        }
        await session.commit()

    response = await check_in(client, users["owner"].id, completed=9, total=10)
    assert response.status_code == 200, response.text
    impact = response.json()["feedback"]["plan_impact"]
    assert impact["status"] == "pending_choice"
    assert impact["reason"] == "等你确认风险处理方式后才会生效"
    assert impact["direction"] is None
    feedback = response.json()["feedback"]
    assert feedback["completion"]["completed_sets"] == 9
    assert feedback["comparison"]["has_previous"] is False
    assert feedback["recovery"]["tips"]


@pytest.mark.asyncio
async def test_stats_recent_record_reprojects_feedback_after_refresh(
    client, users, active_plan, background_tasks, session_factory
):
    """刷新后仍能读回反馈：统计里的最近记录按作业当前状态重新投影。"""
    first = await check_in(client, users["owner"].id, completed=9, total=10)
    assert first.status_code == 200, first.text
    await background_tasks[0]

    stats = await client.get(
        f"/api/workout/{users['owner'].id}/stats", headers=_auth(users["owner"].id)
    )
    assert stats.status_code == 200, stats.text
    recent = stats.json()["recent_records"][0]
    assert recent["id"] == first.json()["id"]
    assert recent["feedback"]["plan_impact"]["status"] == "applied"

    explanation = (await current_plan(client, users["owner"].id))["explanation"][
        "latest_adjustment"
    ]
    assert recent["feedback"]["plan_impact"]["direction"] == explanation["direction"]
    assert recent["feedback"]["plan_impact"]["reason"] == explanation["reason"]


@pytest.mark.asyncio
async def test_duplicate_same_day_checkin_is_idempotent(
    client, users, active_plan, background_tasks, session_factory
):
    """AC6：同一天只有一条记录、一个作业，第二次返回同一结果。"""
    await seed_session(session_factory, users["owner"].id, total=10, completed=6)

    first = await check_in(client, users["owner"].id)
    second = await check_in(client, users["owner"].id, completed=1, total=10)

    assert first.status_code == second.status_code == 200
    first_body, second_body = first.json(), second.json()
    assert first_body["id"] == second_body["id"]
    assert first_body["job_id"] == second_body["job_id"]
    assert second_body["completion_rate"] == pytest.approx(0.6)
    assert second_body["feedback"] == first_body["feedback"]
    assert await row_count(session_factory, WorkoutRecord) == 1
    assert await row_count(session_factory, PlanAdjustmentJob) == 1
    assert len(background_tasks) == 1


@pytest.mark.asyncio
async def test_comparison_uses_previous_checkin_and_reports_delta_points(
    client, users, active_plan, background_tasks, session_factory
):
    """AC5：有上一条打卡时给差值（百分点）与方向；首次不伪造「提升 100%」。"""
    await seed_record(
        session_factory,
        users["owner"].id,
        when=YESTERDAY,
        completion_rate=0.8,
        completed=8,
    )
    await seed_session(session_factory, users["owner"].id, total=10, completed=6)

    response = await check_in(client, users["owner"].id, completed=10, total=10)
    assert response.status_code == 200, response.text
    comparison = response.json()["feedback"]["comparison"]

    assert comparison["has_previous"] is True
    assert comparison["previous_completion_rate"] == pytest.approx(0.8)
    assert comparison["delta_percent"] == pytest.approx(-20.0)
    assert comparison["direction"] == "down"
