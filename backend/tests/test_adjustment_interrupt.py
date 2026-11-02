"""HITL interrupt / resume 的路由层契约（工单 27）。

命中风险条件时作业挂在 ``pending_choice``：计划一行不动、没有调整结论记录，
用户选完才落地；用户 5 分钟不回来，系统按推荐（保守）方案代为落地并标明
``chosen_by=timeout_default``。重复提交同一选项幂等，提交不同选项是冲突。
超时兜底两条路径都要覆盖：创建中断时投递的延迟任务，以及读取/恢复时的惰性收敛。
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

import app.services.plan.adjustment_job_service as job_service_module
import app.services.workout.workout_service as workout_service_module
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.adjustment import PlanAdjustment
from app.models.adjustment_job import PlanAdjustmentJob
from app.models.plan import TrainingPlan
from app.models.user import User
from app.services.plan import interrupt_policy
from app.services.plan.interrupt_policy import (
    INTERRUPT_TTL_SECONDS,
    InterruptSignal,
    detect_interrupt,
)

TODAY = datetime.date.today()


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
    db_path = tmp_path / "adjustment-interrupt.db"
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
        owner = User(openid="interrupt-owner", nickname="Owner")
        other = User(openid="interrupt-other", nickname="Other")
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
    """捕获打卡后投递的评估协程，让测试决定它何时执行。"""
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
def timeout_tasks(monkeypatch):
    """捕获中断创建时投递的延迟兜底任务，避免测试里真的等 5 分钟。"""
    captured: list = []

    def _capture(coroutine):
        captured.append(coroutine)
        return types.SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        job_service_module, "asyncio", types.SimpleNamespace(create_task=_capture)
    )
    yield captured
    for coroutine in captured:
        coroutine.close()


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


async def resume(client, user_id: int, job_id: str, option_id: str, *, actor_id: int | None = None):
    return await client.post(
        f"/api/plan/{user_id}/adjustments/jobs/{job_id}/resume",
        json={"option_id": option_id},
        headers=_auth(actor_id if actor_id is not None else user_id),
    )


async def pending_jobs(client, user_id: int):
    return await client.get(
        f"/api/plan/{user_id}/adjustments/jobs/pending", headers=_auth(user_id)
    )


async def seed_applied_jobs(session_factory, user_id: int, deltas: list[float]) -> None:
    """历史里已经有几次大幅调整：命中「连续 3 次 >20%」的触发条件。"""
    async with session_factory() as session:
        for index, delta in enumerate(deltas):
            session.add(
                PlanAdjustmentJob(
                    job_id=f"job_seed_{index:02d}",
                    user_id=user_id,
                    status="applied",
                    landed_at=datetime.datetime.now(datetime.timezone.utc),
                    decision={
                        "direction": "increase",
                        "delta_percent": delta,
                        "exercise_swaps": [],
                        "rest_day_change": None,
                    },
                )
            )
        await session.commit()


async def seed_pending_job(
    session_factory, user_id: int, job_id: str
) -> datetime.datetime:
    """直接写入一条待选择作业：用于归属 / 选项校验等不需要重新评估的用例。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    signal = InterruptSignal(
        reason_codes=(interrupt_policy.REASON_INJURY_RISK,),
        summary="伤病风险偏高，请先确认本次调整",
        evidence={"injury_score": 2.0},
    )
    payload = interrupt_policy.build_interrupt_payload(
        signal,
        now=now,
        evaluation={
            "completion_rate": 0.9,
            "difficulty_rating": 3.0,
            "dimensions": [_injury(2.0)],
            "merged": {"overall_score": 9.0, "red_flags": []},
        },
    )
    async with session_factory() as session:
        session.add(
            PlanAdjustmentJob(
                job_id=job_id,
                user_id=user_id,
                status="pending_choice",
                interrupt=payload,
                interrupt_expires_at=now + datetime.timedelta(seconds=INTERRUPT_TTL_SECONDS),
            )
        )
        await session.commit()
    return now


async def plan_snapshot(session_factory, plan_id: int) -> dict:
    async with session_factory() as session:
        plan = await session.get(TrainingPlan, plan_id)
        assert plan is not None
        return {
            "difficulty_factor": plan.difficulty_factor,
            "weekly_plan": plan.weekly_plan,
            "latest_adjustment_id": plan.latest_adjustment_id,
        }


async def plan_factor(session_factory, plan_id: int) -> float:
    return (await plan_snapshot(session_factory, plan_id))["difficulty_factor"]


async def adjustment_count(session_factory) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(select(func.count()).select_from(PlanAdjustment)) or 0
        )


async def load_job(session_factory, job_id: str) -> PlanAdjustmentJob:
    async with session_factory() as session:
        job = await session.get(PlanAdjustmentJob, job_id)
        assert job is not None
        return job


async def create_interrupt_job(
    client, users, active_plan, background_tasks, session_factory
) -> tuple[str, dict]:
    """制造一次必须中断的打卡：先写入 3 次 >20% 的历史调整。"""
    await seed_applied_jobs(session_factory, users["owner"].id, [25.0, 32.0, 21.0])
    before = await plan_snapshot(session_factory, active_plan.id)
    response = await check_in(client, users["owner"].id)
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    assert background_tasks, "打卡后应投递一次评估"
    await background_tasks[-1]
    return job_id, before


def _future(seconds: int = INTERRUPT_TTL_SECONDS + 5) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=seconds
    )


# ---------------------------------------------------------------------------
# 纯函数：三个触发条件与固定三选一
# ---------------------------------------------------------------------------


def _injury(score: float, completeness: str = "full") -> dict:
    return {
        "name": "injury_risk",
        "score": score,
        "reason": "伤病风险依据",
        "suggestion": "降低强度",
        "source": "rule",
        "degraded": False,
        "data_completeness": completeness,
    }


def test_injury_dimension_triggers_unless_it_is_the_default_placeholder():
    signal = detect_interrupt(
        dimensions=[_injury(2.0)], merged={"overall_score": 4.0}, recent_deltas=[]
    )
    assert isinstance(signal, InterruptSignal)
    assert signal.triggered is True
    assert signal.reason_codes == (interrupt_policy.REASON_INJURY_RISK,)
    assert signal.evidence["injury_score"] == pytest.approx(2.0)
    assert "伤病" in signal.summary

    # 数据缺省时评分只是中性占位，不构成风险信号。
    placeholder = detect_interrupt(
        dimensions=[_injury(2.0, completeness="default")],
        merged={"overall_score": 5.0},
        recent_deltas=[],
    )
    assert placeholder.triggered is False


def test_three_most_recent_large_deltas_trigger_interrupt():
    hit = detect_interrupt(
        dimensions=[],
        merged={"overall_score": 6.0},
        recent_deltas=[25.0, 30.0, 21.0],
    )
    assert hit.triggered is True
    assert hit.reason_codes == (interrupt_policy.REASON_FREQUENT_LARGE,)
    assert hit.evidence["recent_deltas"] == [25.0, 30.0, 21.0]

    # 只有两次、或其中一次正好 20%（要求严格大于）都不算命中。
    assert detect_interrupt(
        dimensions=[], merged={}, recent_deltas=[25.0, 30.0]
    ).triggered is False
    assert detect_interrupt(
        dimensions=[], merged={}, recent_deltas=[25.0, 30.0, 20.0]
    ).triggered is False


def test_goal_conflict_red_flag_triggers_interrupt():
    merged = {
        "overall_score": 6.0,
        "red_flags": [
            {"code": "goal_conflict", "severity": "high", "evidence": "减脂期体重上升"},
            {"code": "fatigue_high", "severity": "medium", "evidence": "疲劳 5"},
        ],
    }
    signal = detect_interrupt(dimensions=[], merged=merged, recent_deltas=[])
    assert signal.triggered is True
    assert signal.reason_codes == (interrupt_policy.REASON_GOAL_CONFLICT,)
    assert signal.evidence["red_flags"][0]["code"] == "goal_conflict"

    # 只出现非目标冲突的红标志不中断：日常小幅调整应该安静发生。
    quiet = detect_interrupt(
        dimensions=[],
        merged={"red_flags": [{"code": "fatigue_high", "severity": "medium"}]},
        recent_deltas=[],
    )
    assert quiet.triggered is False


def test_payload_has_exactly_three_stable_options_and_expiry():
    signal = detect_interrupt(
        dimensions=[_injury(2.0)], merged={}, recent_deltas=[30.0, 25.0, 21.0]
    )
    assert set(signal.reason_codes) == {
        interrupt_policy.REASON_INJURY_RISK,
        interrupt_policy.REASON_FREQUENT_LARGE,
    }
    now = datetime.datetime(2026, 11, 2, 10, 0, tzinfo=datetime.timezone.utc)
    payload = interrupt_policy.build_interrupt_payload(
        signal, now=now, evaluation={"completion_rate": 0.9}
    )

    assert payload["reason_codes"] == list(signal.reason_codes)
    assert payload["summary"]
    assert payload["evidence"]
    options = payload["options"]
    assert [option["id"] for option in options] == [
        "reduce_intensity",
        "keep_current",
        "increase_gradually",
    ]
    assert options[0]["recommended"] is True
    assert all(option["recommended"] is False for option in options[1:])
    for option in options:
        assert {
            "id",
            "label",
            "description",
            "direction",
            "magnitude_percent",
            "recommended",
        } <= set(option)
    assert options[0]["direction"] == "decrease"
    assert 15.0 <= options[0]["magnitude_percent"] <= 20.0
    assert options[1]["direction"] == "keep"
    assert options[1]["magnitude_percent"] == 0.0
    assert options[2]["direction"] == "increase"
    assert options[2]["magnitude_percent"] == pytest.approx(5.0)
    assert payload["expires_at"] == (now + datetime.timedelta(seconds=300)).isoformat()
    assert payload["evaluation"] == {"completion_rate": 0.9}
    assert interrupt_policy.recommended_option(payload)["id"] == "reduce_intensity"
    assert interrupt_policy.find_option(payload, "keep_current")["id"] == "keep_current"
    assert interrupt_policy.find_option(payload, "nope") is None


# ---------------------------------------------------------------------------
# AC1：命中条件时挂起，计划一行不动
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interrupt_payload_keeps_plan_untouched_and_job_pending(
    client, users, active_plan, background_tasks, session_factory
):
    job_id, before = await create_interrupt_job(
        client, users, active_plan, background_tasks, session_factory
    )

    assert await plan_snapshot(session_factory, active_plan.id) == before
    assert await adjustment_count(session_factory) == 0

    detail = await get_detail(client, users["owner"].id, job_id)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "pending_choice"
    assert body["landed"] is False
    assert body["landed_at"] is None
    assert body["chosen_by"] is None
    assert body["chosen_option"] is None
    assert body["interrupt_expires_at"]

    interrupt = body["interrupt"]
    assert "frequent_large_adjustment" in interrupt["reason_codes"]
    assert isinstance(interrupt["summary"], str) and interrupt["summary"]
    assert sorted(interrupt["evidence"]["recent_deltas"]) == [21.0, 25.0, 32.0]
    assert len(interrupt["options"]) == 3
    assert interrupt["options"][0]["recommended"] is True
    expires_at = datetime.datetime.fromisoformat(interrupt["expires_at"])
    expires_column = datetime.datetime.fromisoformat(body["interrupt_expires_at"])
    if expires_column.tzinfo is None:
        expires_column = expires_column.replace(tzinfo=datetime.timezone.utc)
    assert (expires_at - expires_column).total_seconds() == pytest.approx(0, abs=1)
    assert expires_at > datetime.datetime.now(datetime.timezone.utc)

    pending = await pending_jobs(client, users["owner"].id)
    assert pending.status_code == 200
    items = pending.json()
    assert [item["job_id"] for item in items] == [job_id]
    assert items[0]["status"] == "pending_choice"
    assert items[0]["interrupt"]["options"][0]["id"] == "reduce_intensity"


@pytest.mark.asyncio
async def test_non_interrupt_job_stays_applied_without_interrupt_payload(
    client, users, active_plan, background_tasks, session_factory
):
    response = await check_in(client, users["owner"].id)
    job_id = response.json()["job_id"]
    await background_tasks[-1]

    detail = await get_detail(client, users["owner"].id, job_id)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "applied"
    assert body["interrupt"] is None
    assert body["interrupt_expires_at"] is None
    assert body["chosen_by"] is None
    assert body["chosen_option"] is None

    pending = await pending_jobs(client, users["owner"].id)
    assert pending.status_code == 200
    assert pending.json() == []


# ---------------------------------------------------------------------------
# AC3：用户选择后落地，记录是谁选的、选了哪个
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_resume_applies_chosen_option_and_records_choice(
    client, users, active_plan, background_tasks, session_factory
):
    job_id, before = await create_interrupt_job(
        client, users, active_plan, background_tasks, session_factory
    )

    response = await resume(client, users["owner"].id, job_id, "reduce_intensity")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["job_id"] == job_id
    assert body["status"] == "applied"
    assert body["landed"] is True
    assert body["landed_at"]
    assert body["chosen_by"] == "user"
    assert body["chosen_option"] == "reduce_intensity"
    assert body["adjustment_id"].startswith("adj_")
    assert body["decision"]["direction"] == "decrease"
    assert body["decision"]["delta_percent"] == pytest.approx(15.0)
    assert body["dimensions"], "落地结论应保留评估明细"
    assert [entry["name"] for entry in body["dimensions"]] == [
        "completion",
        "fatigue",
        "injury_risk",
        "sleep",
        "body_composition",
    ]
    assert body["merged"]["overall_score"] == pytest.approx(9.0)
    assert body["plan_diff"]["before_difficulty_factor"] == pytest.approx(
        before["difficulty_factor"]
    )
    assert body["plan_diff"]["after_difficulty_factor"] == pytest.approx(0.85)

    after = await plan_snapshot(session_factory, active_plan.id)
    assert after["difficulty_factor"] == pytest.approx(0.85)
    assert after["weekly_plan"] == before["weekly_plan"]
    assert after["latest_adjustment_id"] == body["adjustment_id"]

    async with session_factory() as session:
        record = await session.get(PlanAdjustment, body["adjustment_id"])
        assert record is not None
        assert record.direction == "decrease"
        assert record.delta_percent == pytest.approx(15.0)
        assert record.plan_id == active_plan.id
        assert "降低强度" in record.reason
        assert record.dimensions
        assert record.merged

    assert await adjustment_count(session_factory) == 1
    assert (await pending_jobs(client, users["owner"].id)).json() == []


# ---------------------------------------------------------------------------
# AC4：幂等与冲突
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeating_the_same_option_is_idempotent_and_a_different_option_conflicts(
    client, users, active_plan, background_tasks, session_factory
):
    job_id, _ = await create_interrupt_job(
        client, users, active_plan, background_tasks, session_factory
    )

    first = await resume(client, users["owner"].id, job_id, "reduce_intensity")
    assert first.status_code == 200, first.text
    landed = first.json()
    assert landed["status"] == "applied"

    second = await resume(client, users["owner"].id, job_id, "reduce_intensity")
    assert second.status_code == 200, second.text
    assert second.json() == landed
    assert await plan_factor(session_factory, active_plan.id) == pytest.approx(0.85)
    assert await adjustment_count(session_factory) == 1

    conflict = await resume(client, users["owner"].id, job_id, "keep_current")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "adjustment_already_decided"
    assert await plan_factor(session_factory, active_plan.id) == pytest.approx(0.85)
    assert await adjustment_count(session_factory) == 1
    assert (await load_job(session_factory, job_id)).chosen_option == "reduce_intensity"


# ---------------------------------------------------------------------------
# AC5：超时兜底（延迟任务 + 读取时惰性收敛）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delayed_timeout_task_applies_recommended_option_once(
    client, users, active_plan, background_tasks, session_factory, timeout_tasks, monkeypatch
):
    job_id, before = await create_interrupt_job(
        client, users, active_plan, background_tasks, session_factory
    )
    assert len(timeout_tasks) == 1, "中断创建后应投递一次延迟兜底"

    slept: list[float] = []

    async def _instant_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(job_service_module, "_async_sleep", _instant_sleep)
    monkeypatch.setattr(job_service_module, "AsyncSessionLocal", session_factory)
    future = _future()
    monkeypatch.setattr(job_service_module, "utc_now", lambda: future)

    await timeout_tasks[0]

    assert slept == [INTERRUPT_TTL_SECONDS]
    job = await load_job(session_factory, job_id)
    assert job.status == "expired_no_choice"
    assert job.chosen_by == "timeout_default"
    assert job.chosen_option == "reduce_intensity"
    assert job.adjustment_id
    assert await plan_factor(session_factory, active_plan.id) == pytest.approx(0.85)
    assert await adjustment_count(session_factory) == 1

    detail = (await get_detail(client, users["owner"].id, job_id)).json()
    assert detail["status"] == "expired_no_choice"
    assert detail["landed"] is True
    assert detail["chosen_by"] == "timeout_default"
    assert detail["decision"]["direction"] == "decrease"

    # 过期后再选择：明确答复「已按保守方案应用」，且不再改计划。
    late = await resume(client, users["owner"].id, job_id, "increase_gradually")
    assert late.status_code == 200, late.text
    assert late.json()["status"] == "expired_no_choice"
    assert late.json()["chosen_by"] == "timeout_default"
    assert await plan_factor(session_factory, active_plan.id) == pytest.approx(0.85)
    assert await adjustment_count(session_factory) == 1


@pytest.mark.asyncio
async def test_expired_interrupt_is_reconciled_on_read_after_restart(
    client, users, active_plan, background_tasks, session_factory, timeout_tasks, monkeypatch
):
    job_id, _ = await create_interrupt_job(
        client, users, active_plan, background_tasks, session_factory
    )
    # 模拟进程重启：延迟任务从未执行（测试里从未 await），只靠读取时收敛。
    future = _future()
    monkeypatch.setattr(job_service_module, "utc_now", lambda: future)

    detail = await get_detail(client, users["owner"].id, job_id)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "expired_no_choice"
    assert body["chosen_by"] == "timeout_default"
    assert body["chosen_option"] == "reduce_intensity"
    assert await plan_factor(session_factory, active_plan.id) == pytest.approx(0.85)
    assert await adjustment_count(session_factory) == 1

    # 再读一次：同一终态，计划只被改动一次。
    again = (await get_detail(client, users["owner"].id, job_id)).json()
    assert again["status"] == "expired_no_choice"
    assert again["adjustment_id"] == body["adjustment_id"]
    assert await plan_factor(session_factory, active_plan.id) == pytest.approx(0.85)
    assert await adjustment_count(session_factory) == 1

    pending = await pending_jobs(client, users["owner"].id)
    assert pending.json() == []

    late = await resume(client, users["owner"].id, job_id, "keep_current")
    assert late.status_code == 200, late.text
    assert late.json()["status"] == "expired_no_choice"
    assert late.json()["chosen_by"] == "timeout_default"
    assert await plan_factor(session_factory, active_plan.id) == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# 归属与稳定错误码
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_other_users_cannot_resume_someone_elses_choice(
    client, users, active_plan, background_tasks, session_factory
):
    job_id, before = await create_interrupt_job(
        client, users, active_plan, background_tasks, session_factory
    )

    # 通过别人的用户路径访问：既有守卫先拒绝。
    through_owner_path = await resume(
        client,
        users["owner"].id,
        job_id,
        "reduce_intensity",
        actor_id=users["other"].id,
    )
    assert through_owner_path.status_code == 403
    assert through_owner_path.json()["detail"] == "无权访问其他用户的数据"

    # 用自己的用户路径替别人拍板：403 且不泄漏内容。
    own_path = await resume(
        client,
        users["other"].id,
        job_id,
        "reduce_intensity",
        actor_id=users["other"].id,
    )
    assert own_path.status_code == 403
    assert own_path.json()["detail"]["code"] == "adjustment_job_forbidden"

    still_pending = (await get_detail(client, users["owner"].id, job_id)).json()
    assert still_pending["status"] == "pending_choice"
    assert still_pending["chosen_by"] is None
    assert await plan_snapshot(session_factory, active_plan.id) == before
    assert await adjustment_count(session_factory) == 0


@pytest.mark.asyncio
async def test_unknown_job_invalid_option_and_not_pending_have_stable_codes(
    client, users, active_plan, background_tasks, session_factory
):
    missing = await resume(client, users["owner"].id, "job_missing", "reduce_intensity")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "adjustment_job_not_found"

    await seed_pending_job(session_factory, users["owner"].id, "job_pending_invalid")
    invalid = await resume(
        client, users["owner"].id, "job_pending_invalid", "swap_exercise"
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "adjustment_option_invalid"

    response = await check_in(client, users["owner"].id)
    job_id = response.json()["job_id"]

    # 评估还没跑完：没有可选项，不能提前拍板。
    evaluating = await resume(client, users["owner"].id, job_id, "reduce_intensity")
    assert evaluating.status_code == 409
    assert evaluating.json()["detail"]["code"] == "adjustment_not_pending_choice"
    await background_tasks[-1]
