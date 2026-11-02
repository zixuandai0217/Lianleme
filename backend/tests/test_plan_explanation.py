"""计划解释字段（工单 20）的路由层契约测试。

读计划必须能回答两件事：这份计划按什么生成、最近一次为什么被调整。旧计划（没有
解释数据）与残缺快照都不能把读取打挂；既有字段（难度系数等）的类型与含意保持
不变。只断言 HTTP 契约，不测 ORM 内部实现。
"""

import datetime
import json
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
from app.core.security import require_current_user_api_key
from app.main import app
from app.models.plan import TrainingPlan
from app.models.user import User
from app.services.ai.llm_factory import LLMClientFactory

WEEK_START = datetime.date(2026, 3, 16)

PROFILE = {"height": 178, "weight": 72.0, "goal": "增肌", "experience": "中级"}
ANALYSIS = {
    "body_type": "mesomorph",
    "body_fat_range": "18-22%",
    "weak_muscles": ["上肢拉力", "核心"],
    "strengths": ["下肢"],
    "muscle_scores": {"胸": 6, "腿": 8},
    "summary": "下肢力量突出，建议优先补齐上肢拉力与核心稳定性。",
}


def week_plan() -> list[dict]:
    """七天计划：每天一个动作，足够让调整链路与读取都有对象。"""
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


def generated_plan_payload() -> str:
    """模型替身回给生成链路的合法计划 JSON（TrainingPlanSchema 形状）。"""
    return json.dumps(
        {
            "user_id": 0,
            "week_start": WEEK_START.isoformat(),
            "weekly_plan": week_plan(),
            "difficulty_factor": 1.0,
            "status": "active",
        },
        ensure_ascii=False,
    )


class _OfflineLLM:
    """离线模型替身：生成与打卡反馈都不联网。"""

    async def ainvoke(self, messages):
        return types.SimpleNamespace(content=generated_plan_payload())


class _FakeAdjuster:
    """复刻 AdjustGraph 的出口（方向 + 理由），不调用 LLM。"""

    def __init__(self, user_id: int, db=None):
        self.user_id = user_id
        self.db = db

    async def run(self, completion_rate, difficulty_rating, current_plan) -> dict:
        if completion_rate >= 0.8:
            direction = "increase"
            reason = f"完成率 {completion_rate:.0%}，表现优秀，适当加量"
        elif completion_rate < 0.5:
            direction = "decrease"
            reason = f"完成率 {completion_rate:.0%}，难度过高，适当减量"
        else:
            direction = "keep"
            reason = f"完成率 {completion_rate:.0%}，保持当前难度"
        return {
            "user_id": self.user_id,
            "completion_rate": completion_rate,
            "difficulty_rating": difficulty_rating,
            "current_plan": current_plan,
            "adjustment_type": direction,
            "adjusted_plan": current_plan,
            "reason": reason,
        }


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """隔离的 SQLite 库，避免污染 dev.db。"""
    db_path = tmp_path / "plan-explanation.db"
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
        owner = User(openid="explain-owner", nickname="Owner")
        other = User(openid="explain-other", nickname="Other")
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


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    """模型替身：生成与打卡反馈都走本地假响应，绝不联网。"""

    async def fake_get_client(self, *args, **kwargs):
        return _OfflineLLM()

    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)


@pytest.fixture(autouse=True)
def fake_adjuster(monkeypatch):
    """调整图替身：只复刻出口形状（方向 + 理由）。"""
    monkeypatch.setattr(plan_service_module, "AdjustGraph", _FakeAdjuster)


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


@pytest.fixture
def ai_key_guard(session_factory, users):
    """生成路由的密钥门禁替身：本工单关心落库与读取，不重复验证 BYOK 门禁。"""

    async def _owner() -> User:
        async with session_factory() as session:
            return await session.get(User, users["owner"].id)

    app.dependency_overrides[require_current_user_api_key] = _owner
    yield
    app.dependency_overrides.pop(require_current_user_api_key, None)


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def current_plan(client, user_id: int) -> dict:
    """读取当前计划；解释字段的断言都在这个响应上做。"""
    response = await client.get(f"/api/plan/{user_id}/current", headers=_auth(user_id))
    assert response.status_code == 200, response.text
    return response.json()


async def check_in(client, user_id: int, *, completed: int, total: int):
    """提交一次打卡；返回响应，由调用方断言状态码。"""
    return await client.post(
        "/api/workout/complete",
        json={
            "user_id": user_id,
            "workout_date": WEEK_START.isoformat(),
            "total_sets": total,
            "completed_sets": completed,
            "duration_minutes": 30,
            "difficulty_rating": 3,
        },
        headers=_auth(user_id),
    )


async def seed_plan(
    factory,
    user_id: int,
    *,
    week_start: datetime.date = WEEK_START,
    snapshot: dict | None = None,
    profile_snapshot: dict | None = None,
    captured_at: datetime.datetime | None = None,
    difficulty_factor: float = 1.0,
    latest_adjustment_id: str | None = None,
) -> None:
    """直接铺一条计划行：覆盖「旧数据」「部分快照」等读取场景。"""
    async with factory() as session:
        session.add(
            TrainingPlan(
                user_id=user_id,
                week_start=week_start,
                weekly_plan=week_plan(),
                body_analysis_snapshot=snapshot,
                profile_snapshot=profile_snapshot,
                analysis_captured_at=captured_at,
                difficulty_factor=difficulty_factor,
                latest_adjustment_id=latest_adjustment_id,
                status="active",
            )
        )
        await session.commit()


async def fill_profile_and_analysis(factory, user_id: int) -> None:
    """把档案与体型分析放进用户行：生成接口自己从库里读，前端无须重复上传。"""
    async with factory() as session:
        user = await session.get(User, user_id)
        user.profile = PROFILE
        user.body_analysis = ANALYSIS
        await session.commit()


@pytest.mark.asyncio
async def test_generated_plan_exposes_generation_basis(
    client, users, session_factory, ai_key_guard
):
    """AC2：生成计划后读取当前计划能拿到生成依据（含分析时间与生成时档案目标）。"""
    await fill_profile_and_analysis(session_factory, users["owner"].id)

    generated = await client.post(
        "/api/plan/generate",
        json={"user_id": users["owner"].id, "week_start": WEEK_START.isoformat()},
        headers=_auth(users["owner"].id),
    )
    assert generated.status_code == 200, generated.text

    body = await current_plan(client, users["owner"].id)
    explanation = body["explanation"]
    generation = explanation["generation"]

    assert generation["body_type"] in ("ectomorph", "mesomorph", "endomorph")
    assert generation["body_type"] == "mesomorph"
    assert generation["body_fat_range"] == "18-22%"
    assert generation["weak_muscles"] == ["上肢拉力", "核心"]
    assert generation["strengths"] == ["下肢"]
    assert generation["analysis_summary"] == ANALYSIS["summary"]
    assert generation["captured_at"], "该次分析的时间必须可读"
    assert generation["profile_goal"] == "增肌"
    assert explanation["latest_adjustment"] is None


@pytest.mark.asyncio
async def test_checkin_adjustment_is_readable_from_the_plan(
    client, users, session_factory, background_tasks
):
    """AC1：打卡触发调整后，计划读取带出方向、完成率触发指标、时间与理由。"""
    await seed_plan(session_factory, users["owner"].id)

    response = await check_in(client, users["owner"].id, completed=8, total=10)
    assert response.status_code == 200, response.text
    assert background_tasks, "打卡后应调度一次调整"
    await background_tasks[0]

    explanation = (await current_plan(client, users["owner"].id))["explanation"]
    adjustment = explanation["latest_adjustment"]

    assert adjustment is not None
    assert adjustment["direction"] in ("increase", "decrease", "keep")
    assert adjustment["direction"] == "increase"
    assert adjustment["trigger"] == "completion_rate"
    assert adjustment["completion_rate"] == pytest.approx(0.8)
    assert adjustment["occurred_at"], "调整发生时间必须可读"
    assert adjustment["reason"]
    assert "80%" in adjustment["reason"]
    # 该计划没有生成快照，生成依据照常为空，不影响调整说明。
    assert explanation["generation"] is None


@pytest.mark.asyncio
async def test_keep_direction_is_an_explanation_not_a_missing_record(
    client, users, session_factory, background_tasks
):
    """AC1 对照：方向为 keep 时也是真实的调整说明，不能读成「没有调整」。"""
    await seed_plan(session_factory, users["owner"].id)

    response = await check_in(client, users["owner"].id, completed=6, total=10)
    assert response.status_code == 200, response.text
    await background_tasks[0]

    adjustment = (await current_plan(client, users["owner"].id))["explanation"][
        "latest_adjustment"
    ]
    assert adjustment is not None
    assert adjustment["direction"] == "keep"
    assert adjustment["completion_rate"] == pytest.approx(0.6)
    assert adjustment["reason"]


@pytest.mark.asyncio
async def test_old_plan_without_explanation_data_still_reads(client, users, session_factory):
    """AC3：存量旧计划（没有快照、没有调整记录）读取成功，两个解释子对象均为 null。"""
    await seed_plan(session_factory, users["owner"].id)

    body = await current_plan(client, users["owner"].id)

    assert body["explanation"] == {"generation": None, "latest_adjustment": None}
    assert body["plan"]["weekly_plan"], "旧计划的动作清单照常返回"


@pytest.mark.asyncio
async def test_partially_filled_snapshot_degrades_per_field(client, users, session_factory):
    """AC3：只填了部分子字段的快照也能读取，缺失子字段为 null 而不是整块消失。"""
    await seed_plan(
        session_factory,
        users["owner"].id,
        snapshot={"body_type": "endomorph"},
        profile_snapshot=None,
        captured_at=None,
    )

    body = await current_plan(client, users["owner"].id)

    generation = body["explanation"]["generation"]
    assert generation is not None
    assert generation["body_type"] == "endomorph"
    for missing in (
        "body_fat_range",
        "weak_muscles",
        "strengths",
        "analysis_summary",
        "captured_at",
        "profile_goal",
    ):
        assert generation[missing] is None, f"{missing} 缺失时应为 null"

    # 有快照但没有档案目标：目标无法定位，其余字段照常。用更晚的周起始日保证读到的是
    # 这条（读取路径按周起始日取最新的 active 计划）。
    await seed_plan(
        session_factory,
        users["owner"].id,
        week_start=WEEK_START + datetime.timedelta(days=7),
        snapshot=ANALYSIS,
        profile_snapshot={"height": 178},
        captured_at=datetime.datetime(2026, 3, 15, 9, 0, tzinfo=datetime.timezone.utc),
    )
    complete = (await current_plan(client, users["owner"].id))["explanation"]["generation"]
    assert complete["profile_goal"] is None, "档案缺 goal 时不得伪造目标"
    assert complete["captured_at"], "快照带了时间就必须透出"


@pytest.mark.asyncio
async def test_unexpected_snapshot_value_types_do_not_break_the_read(
    client, users, session_factory
):
    """AC3：快照里出现非预期类型（列表写成字符串）时读取仍成功，不抛 5xx。"""
    await seed_plan(
        session_factory,
        users["owner"].id,
        snapshot={
            "body_type": "endomorph",
            "weak_muscles": "下肢",  # 模型偶发把列表写成字符串
            "strengths": None,
            "summary": None,
        },
        profile_snapshot={"goal": ""},
    )

    generation = (await current_plan(client, users["owner"].id))["explanation"]["generation"]

    assert generation["weak_muscles"] == ["下肢"]
    assert generation["strengths"] is None
    assert generation["analysis_summary"] is None
    assert generation["profile_goal"] is None


@pytest.mark.asyncio
async def test_plan_pointing_at_a_missing_adjustment_reads_as_no_adjustment(
    client, users, session_factory
):
    """AC3 相邻：引用指向的记录不存在（无外键，可能被清理）时降级为「没有调整」。"""
    await seed_plan(
        session_factory, users["owner"].id, latest_adjustment_id="adj_missing_record"
    )

    explanation = (await current_plan(client, users["owner"].id))["explanation"]

    assert explanation["latest_adjustment"] is None


@pytest.mark.asyncio
async def test_existing_plan_fields_keep_type_and_meaning(client, users, session_factory):
    """AC5：新增解释结构不改变既有字段的类型与含意（难度系数等仍原样可读）。"""
    await seed_plan(session_factory, users["owner"].id, difficulty_factor=1.15)

    body = await current_plan(client, users["owner"].id)
    plan = body["plan"]

    assert body["message"] == "获取成功"
    assert isinstance(plan["difficulty_factor"], float)
    assert plan["difficulty_factor"] == pytest.approx(1.15)
    assert plan["status"] == "active"
    assert plan["week_start"] == WEEK_START.isoformat()
    assert isinstance(plan["weekly_plan"], list) and len(plan["weekly_plan"]) == 7
    first_day = plan["weekly_plan"][0]
    assert isinstance(first_day["day"], int) and first_day["day"] == 1
    assert isinstance(first_day["exercises"], list) and first_day["exercises"]
    assert isinstance(first_day["estimated_duration"], int)
    assert "explanation" in body, "解释是新增字段，不替换既有结构"
