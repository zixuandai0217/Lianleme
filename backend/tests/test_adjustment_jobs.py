"""可查询调整作业的路由层契约（工单 26）。

打卡只负责「投递」：响应立刻带作业标识，评估在后台推进；作业的五维小结、
合并分、决策、计划前后差异与失败分类都从数据库读出，所以刷新、换设备、
进程重启后看到的都是同一份事实。
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
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.plan.plan_service as plan_service_module
import app.services.workout.workout_service as workout_service_module
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.adjustment import PlanAdjustment
from app.models.adjustment_job import PlanAdjustmentJob
from app.models.plan import TrainingPlan
from app.models.user import User

TODAY = datetime.date.today()
DIMENSION_ORDER = [
    "completion",
    "fatigue",
    "injury_risk",
    "sleep",
    "body_composition",
]


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


@pytest_asyncio.fixture
async def database(tmp_path: Path):
    """One isolated SQLite file, plus a handle we can reopen to simulate a restart."""
    db_path = tmp_path / "adjustment-jobs.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield {"path": db_path, "engine": engine, "factory": factory}
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(database):
    return database["factory"]


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="job-owner", nickname="Owner")
        other = User(openid="job-other", nickname="Other")
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
    """Capture the post-check-in coroutine so tests decide when evaluation runs."""
    captured: list = []

    def _capture(coroutine):
        captured.append(coroutine)
        return types.SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        workout_service_module, "asyncio", types.SimpleNamespace(create_task=_capture)
    )
    monkeypatch.setattr(workout_service_module, "AsyncSessionLocal", session_factory)
    return captured


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def check_in(client, user_id: int, *, completed: int = 9, total: int = 10):
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


async def get_detail(client, user_id: int, job_id: str):
    return await client.get(
        f"/api/plan/{user_id}/adjustments/jobs/{job_id}", headers=_auth(user_id)
    )


async def job_count(session_factory) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(select(func.count()).select_from(PlanAdjustmentJob)) or 0
        )


async def adjustment_count(session_factory) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(select(func.count()).select_from(PlanAdjustment)) or 0
        )


@pytest.mark.asyncio
async def test_checkin_returns_job_id_without_waiting_for_evaluation(
    client, users, active_plan, background_tasks, session_factory
):
    """AC1：打卡 200 且立刻带作业标识；评估仍在后台，作业已持久化。"""
    response = await check_in(client, users["owner"].id)
    assert response.status_code == 200, response.text
    body = response.json()

    job_id = body["job_id"]
    assert job_id.startswith("job_")
    assert body["job_error"] is None
    assert background_tasks, "打卡后应投递一次评估"
    assert await job_count(session_factory) == 1

    # 评估还没跑：作业已经能被读到，状态是「评估中」。
    detail = await get_detail(client, users["owner"].id, job_id)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "evaluating"
    assert payload["landed"] is False
    assert payload["dimensions"] is None
    assert payload["decision"] is None
    assert payload["failure_class"] is None

    # 打卡事实已经提交，不依赖评估完成。
    stats = await client.get(
        f"/api/workout/{users['owner'].id}/stats", headers=_auth(users["owner"].id)
    )
    assert stats.status_code == 200
    assert stats.json()["total_checkins"] == 1

    await background_tasks[0]


@pytest.mark.asyncio
async def test_applied_job_detail_exposes_dimensions_decision_and_plan_diff(
    client, users, active_plan, background_tasks
):
    """AC2/AC5：已应用作业给出五维小结、合并分、决策、前后差异与落地时间。"""
    response = await check_in(client, users["owner"].id)
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    await background_tasks[0]

    detail = await get_detail(client, users["owner"].id, job_id)
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["status"] == "applied"
    assert body["landed"] is True
    assert body["landed_at"]
    assert body["failure_class"] is None
    assert body["error_code"] is None

    dimensions = body["dimensions"]
    assert [entry["name"] for entry in dimensions] == DIMENSION_ORDER
    for entry in dimensions:
        assert {"score", "reason", "suggestion", "source", "degraded", "data_completeness"} <= set(
            entry
        )
    assert dimensions[0]["score"] == 9
    assert dimensions[2]["degraded"] is True

    merged = body["merged"]
    assert merged["overall_score"] == pytest.approx(9.0)
    assert merged["red_flags"] == []
    assert merged["top_reasons"]
    assert merged["excluded_dimensions"]

    decision = body["decision"]
    assert decision["direction"] == "increase"
    assert decision["delta_percent"] == pytest.approx(12.0)
    assert decision["exercise_swaps"] == []
    assert decision["rest_day_change"] is None

    plan_diff = body["plan_diff"]
    assert plan_diff["before_difficulty_factor"] == pytest.approx(1.0)
    assert plan_diff["after_difficulty_factor"] == pytest.approx(1.12)
    assert plan_diff["changed_days"] == []
    assert plan_diff["before_summary"]
    assert plan_diff["after_summary"]


@pytest.mark.asyncio
async def test_pending_list_is_empty_then_lists_unresolved_job(
    client, users, active_plan, background_tasks
):
    """AC3：无未决时 200 空列表；评估中出现在 pending；落地后消失。"""
    empty = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs/pending",
        headers=_auth(users["owner"].id),
    )
    assert empty.status_code == 200
    assert empty.json() == []

    response = await check_in(client, users["owner"].id)
    job_id = response.json()["job_id"]

    pending = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs/pending",
        headers=_auth(users["owner"].id),
    )
    assert pending.status_code == 200
    items = pending.json()
    assert len(items) == 1
    assert items[0]["job_id"] == job_id
    assert items[0]["status"] == "evaluating"
    assert "interrupt" in items[0]
    assert items[0]["interrupt"] is None

    await background_tasks[0]

    after = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs/pending",
        headers=_auth(users["owner"].id),
    )
    assert after.status_code == 200
    assert after.json() == []


@pytest.mark.asyncio
async def test_completed_job_is_repeatable_and_reads_do_not_rewrite_it(
    client, users, active_plan, background_tasks, session_factory
):
    """AC3：终态作业可重复读取同一结果，读取不改写状态。"""
    response = await check_in(client, users["owner"].id)
    job_id = response.json()["job_id"]
    await background_tasks[0]

    first = await get_detail(client, users["owner"].id, job_id)
    second = await get_detail(client, users["owner"].id, job_id)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()

    async with session_factory() as session:
        job = await session.get(PlanAdjustmentJob, job_id)
        assert job is not None
        status_before = job.status
        updated_before = job.updated_at

    third = await get_detail(client, users["owner"].id, job_id)
    assert third.status_code == 200

    async with session_factory() as session:
        job = await session.get(PlanAdjustmentJob, job_id)
        assert job.status == status_before == "applied"
        assert job.updated_at == updated_before


@pytest.mark.asyncio
async def test_crashed_evaluation_projects_as_failed_not_forever_pending(
    client, users, active_plan, background_tasks, session_factory
):
    """崩溃遗留的 evaluating：读取投影为 failed，且不再出现在未决列表。"""
    response = await check_in(client, users["owner"].id)
    job_id = response.json()["job_id"]
    # 这一轮评估永远不会执行：模拟进程在投递后崩溃。
    background_tasks[0].close()

    stale_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
    async with session_factory() as session:
        job = await session.get(PlanAdjustmentJob, job_id)
        assert job is not None
        job.updated_at = stale_at
        await session.commit()

    detail = await get_detail(client, users["owner"].id, job_id)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "failed"
    assert body["failure_class"] == "interrupted"
    assert body["error_code"] == "evaluation_interrupted"
    assert body["landed"] is False

    pending = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs/pending",
        headers=_auth(users["owner"].id),
    )
    assert pending.status_code == 200
    assert pending.json() == []


@pytest.mark.asyncio
async def test_recent_jobs_are_newest_first_and_limit_is_bounded(
    client, users, active_plan, background_tasks
):
    """作业列表按时间倒序，limit 默认 20、上限 100。"""
    first = (await check_in(client, users["owner"].id, completed=9)).json()["job_id"]
    await background_tasks[0]
    second = (await check_in(client, users["owner"].id, completed=2)).json()["job_id"]
    await background_tasks[1]

    response = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs",
        headers=_auth(users["owner"].id),
    )
    assert response.status_code == 200
    jobs = response.json()
    assert [entry["job_id"] for entry in jobs] == [second, first]
    assert all(entry["status"] == "applied" for entry in jobs)

    limited = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs?limit=1",
        headers=_auth(users["owner"].id),
    )
    assert limited.status_code == 200
    assert [entry["job_id"] for entry in limited.json()] == [second]

    too_many = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs?limit=101",
        headers=_auth(users["owner"].id),
    )
    assert too_many.status_code == 422


@pytest.mark.asyncio
async def test_unknown_job_id_is_a_stable_404(client, users):
    response = await get_detail(client, users["owner"].id, "job_missing")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "adjustment_job_not_found"


@pytest.mark.asyncio
async def test_other_users_job_is_forbidden_and_leaks_nothing(
    client, users, active_plan, background_tasks
):
    """AC4：他人作业 403，不返回维度、方向或计划差异内容。"""
    response = await check_in(client, users["owner"].id)
    job_id = response.json()["job_id"]
    await background_tasks[0]

    # 直接访问他人的用户路径：既有守卫先拒绝。
    through_owner_path = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs/{job_id}",
        headers=_auth(users["other"].id),
    )
    assert through_owner_path.status_code == 403

    # 用自己的用户路径访问别人的作业：同样拒绝，且不泄漏内容。
    through_own_path = await get_detail(client, users["other"].id, job_id)
    assert through_own_path.status_code == 403
    assert through_own_path.json()["detail"]["code"] == "adjustment_job_forbidden"
    text = through_own_path.text
    assert "dimensions" not in text
    assert "completion" not in text
    assert "increase" not in text


@pytest.mark.asyncio
async def test_failed_job_has_stable_classification_and_does_not_fake_landing(
    client, users, active_plan, background_tasks, session_factory, monkeypatch
):
    """AC5：失败作业给出稳定失败分类，不伪装成 applied。"""

    async def _provider_boom(self, **kwargs):
        raise RuntimeError("provider timeout 504 upstream-secret")

    monkeypatch.setattr(
        plan_service_module.PlanService, "adjust_plan_after_workout", _provider_boom
    )

    response = await check_in(client, users["owner"].id)
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    await background_tasks[0]

    detail = await get_detail(client, users["owner"].id, job_id)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "failed"
    assert body["failure_class"] == "provider_error"
    assert body["error_code"] == "provider_timeout"
    assert body["landed"] is False
    assert body["landed_at"] is None
    assert body["decision"] is None
    assert body["dimensions"] is None
    assert "upstream-secret" not in detail.text
    assert await adjustment_count(session_factory) == 0


@pytest.mark.asyncio
async def test_invalid_input_and_persist_errors_have_distinct_classifications(
    client, users, active_plan, background_tasks, monkeypatch
):
    async def _invalid(self, **kwargs):
        raise ValueError("completion rate out of range")

    monkeypatch.setattr(plan_service_module.PlanService, "adjust_plan_after_workout", _invalid)
    invalid_checkin = await check_in(client, users["owner"].id)
    invalid_job = invalid_checkin.json()["job_id"]
    await background_tasks[0]
    invalid = (await get_detail(client, users["owner"].id, invalid_job)).json()
    assert invalid["status"] == "failed"
    assert invalid["failure_class"] == "invalid_input"
    assert invalid["error_code"] == "invalid_evaluation_input"

    async def _persist(self, **kwargs):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(plan_service_module.PlanService, "adjust_plan_after_workout", _persist)
    persist_checkin = await check_in(client, users["owner"].id)
    persist_job = persist_checkin.json()["job_id"]
    await background_tasks[1]
    persist = (await get_detail(client, users["owner"].id, persist_job)).json()
    assert persist["status"] == "failed"
    assert persist["failure_class"] == "persist_error"
    assert persist["error_code"] == "adjustment_persist_failed"


@pytest.mark.asyncio
async def test_no_active_plan_fails_the_job_but_keeps_the_checkin(
    client, users, background_tasks
):
    response = await check_in(client, users["owner"].id)
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    await background_tasks[0]

    body = (await get_detail(client, users["owner"].id, job_id)).json()
    assert body["status"] == "failed"
    assert body["failure_class"] == "invalid_input"
    assert body["error_code"] == "no_active_plan"
    assert body["landed"] is False


@pytest.mark.asyncio
async def test_job_survives_process_restart(
    client, database, session_factory, users, active_plan, background_tasks
):
    """AC4：丢弃内存态后，只用数据库仍能读到同一作业与状态。"""
    response = await check_in(client, users["owner"].id)
    job_id = response.json()["job_id"]
    await background_tasks[0]
    before = (await get_detail(client, users["owner"].id, job_id)).json()
    assert before["status"] == "applied"

    # 模拟新进程：旧引擎与会话全部丢弃，仅保留磁盘上的 SQLite 文件。
    await database["engine"].dispose()
    reopened_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database['path'].as_posix()}", future=True
    )
    reopened_factory = async_sessionmaker(bind=reopened_engine, expire_on_commit=False)

    async def reopened_get_db():
        async with reopened_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = reopened_get_db
    try:
        after = await get_detail(client, users["owner"].id, job_id)
        assert after.status_code == 200
        assert after.json() == before
    finally:
        await reopened_engine.dispose()


@pytest.mark.asyncio
async def test_plan_diff_snapshot_survives_later_plan_changes(
    client, users, active_plan, background_tasks
):
    """计划前后差异是评估时的快照：后续调整不会改写旧作业的交代。"""
    first_job = (await check_in(client, users["owner"].id)).json()["job_id"]
    await background_tasks[0]
    first = (await get_detail(client, users["owner"].id, first_job)).json()
    assert first["plan_diff"]["after_difficulty_factor"] == pytest.approx(1.12)

    second_job = (await check_in(client, users["owner"].id)).json()["job_id"]
    await background_tasks[1]
    second = (await get_detail(client, users["owner"].id, second_job)).json()
    assert second["plan_diff"]["before_difficulty_factor"] == pytest.approx(1.12)
    assert second["plan_diff"]["after_difficulty_factor"] == pytest.approx(1.2544)

    again = (await get_detail(client, users["owner"].id, first_job)).json()
    assert again["plan_diff"] == first["plan_diff"]


@pytest.mark.asyncio
async def test_pending_choice_jobs_are_readable_for_the_next_ticket(
    client, users, session_factory
):
    """工单 26 不生产 pending_choice，但读取路径必须能消费工单 27 写入的状态。"""
    interrupt = {
        "reason_code": "injury_risk_high",
        "risk_level": "high",
        "description": "伤病风险偏高",
        "evidence": ["伤病风险健康评分 2.0"],
        "options": [{"id": "reduce_intensity", "label": "降低强度", "recommended": True}],
        "expires_at": "2026-11-02T10:05:00Z",
        "proposed_adjustment": {"direction": "decrease", "delta_percent": 18},
    }
    async with session_factory() as session:
        session.add(
            PlanAdjustmentJob(
                job_id="job_pending_choice_seed",
                user_id=users["owner"].id,
                status="pending_choice",
                interrupt=interrupt,
            )
        )
        await session.commit()

    pending = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/jobs/pending",
        headers=_auth(users["owner"].id),
    )
    assert pending.status_code == 200
    assert [item["job_id"] for item in pending.json()] == ["job_pending_choice_seed"]
    assert pending.json()[0]["interrupt"] == interrupt

    detail = await get_detail(client, users["owner"].id, "job_pending_choice_seed")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "pending_choice"
    assert body["landed"] is False
    assert body["interrupt"] == interrupt


@pytest.mark.asyncio
async def test_job_creation_failure_still_returns_200_with_reason(
    client, users, active_plan, monkeypatch, background_tasks
):
    """AC1 的对照分支：作业没建成时打卡仍然成功，并给出稳定原因。"""

    async def _boom(self, user_id):
        raise SQLAlchemyError("job table unavailable")

    from app.services.plan.adjustment_job_service import AdjustmentJobService

    monkeypatch.setattr(AdjustmentJobService, "create_job", _boom)

    response = await check_in(client, users["owner"].id)
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] is None
    assert body["job_error"] == "job_not_created"
    assert not background_tasks
