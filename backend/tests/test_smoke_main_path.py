"""主链路冒烟：注册 → 登录 → 档案 → 体重 → 今日计划 → 陪练历史。

这条用例不依赖任何外部服务：LLM 在工厂边界替换为确定性反馈，MinIO 禁止访问。
同一旅程的故障金丝雀会把工厂替身改为抛错，并确认反馈断言真的变红。
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import storage
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.services.ai.llm_factory import LLMClientFactory
from app.services.workout.workout_service import WorkoutService

SMOKE_FEEDBACK = "离线模型替身已确认本次训练：注意补水与休息。"


@pytest.fixture(autouse=True)
def offline_boundaries(monkeypatch):
    """无密钥、无存储、无全局 DB 后台任务；只替换外部边界，不绕过路由与鉴权。"""
    for name in ("OPENAI_API_KEY", "QWEN_API_KEY", "QWEN_AUDIO_API_KEY"):
        monkeypatch.setattr(settings, name, "")
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", False)

    def forbidden_storage():
        raise AssertionError("smoke 不得连接真实对象存储")

    async def fake_get_client(self, *args, **kwargs):
        class OfflineLLM:
            async def ainvoke(self, messages):
                return SimpleNamespace(content=SMOKE_FEEDBACK)
        return OfflineLLM()

    async def no_background_adjustment(self, **kwargs):
        # 打卡后的计划调整是 asyncio.create_task 的即发即弃任务，失败只会进事件循环日志、
        # 无法被断言；且它绑定的是应用全局会话（生产 Postgres），会逃出本用例的一次性
        # SQLite。行为由调整链路的单测覆盖，这里只保证 smoke 不依赖任何外部数据库。
        return None

    monkeypatch.setattr(storage, "get_minio_client", forbidden_storage)
    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)
    monkeypatch.setattr(WorkoutService, "_trigger_plan_adjustment", no_background_adjustment)


@pytest_asyncio.fixture
async def smoke_client(tmp_path: Path):
    """独立 SQLite + 依赖覆盖的应用客户端。"""
    db_path = tmp_path / "smoke-main-path.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        # ASGITransport 不启动 lifespan：显式避开生产 DB / bucket 初始化。
        async with AsyncClient(transport=transport, base_url="http://smoke.test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        await engine.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def run_main_path(smoke_client: AsyncClient):
    """一条主链路走到底：任何一环断掉都要在这里先红。"""
    credentials = {"email": "smoke@example.com", "password": "smoke-pass-123"}

    registered = await smoke_client.post(
        "/api/user/register", json={**credentials, "nickname": "冒烟用户"}
    )
    assert registered.status_code == 200, registered.text
    user_id = registered.json()["user_id"]

    logged_in = await smoke_client.post("/api/user/auth/login", json=credentials)
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["token"]
    headers = _auth(token)

    me = await smoke_client.get("/api/user/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json().get("id", me.json().get("user_id")) == user_id

    profile = await smoke_client.put(
        f"/api/user/{user_id}/profile",
        headers=headers,
        json={
            "nickname": "冒烟用户",
            "profile": {
                "height": 178,
                "weight": 72.0,
                "goal": "增肌",
                "experience": "中级",
            },
        },
    )
    assert profile.status_code == 200, profile.text

    weight = await smoke_client.post(
        "/api/weight/record",
        headers=headers,
        json={"user_id": user_id, "weight": 72.0, "note": "冒烟"},
    )
    assert weight.status_code == 200, weight.text

    trend = await smoke_client.get(f"/api/weight/{user_id}/trend", headers=headers)
    assert trend.status_code == 200, trend.text

    # 还没有生成计划：今日与当前计划允许「没有」，但不能 5xx
    plan = await smoke_client.get(f"/api/plan/{user_id}/current", headers=headers)
    assert plan.status_code < 500, plan.text

    today = await smoke_client.get(f"/api/plan/{user_id}/today", headers=headers)
    assert today.status_code < 500, today.text

    # 打卡：主链路的最后一跳（计划调整由后台异步触发，不阻塞打卡响应）
    checkin = await smoke_client.post(
        "/api/workout/complete",
        headers=headers,
        json={
            "user_id": user_id,
            "workout_date": "2026-01-05",
            "total_sets": 12,
            "completed_sets": 10,
            "duration_minutes": 45,
            "difficulty_rating": 3,
        },
    )
    assert checkin.status_code == 200, checkin.text
    # 不能仅断言 200：应用会在 LLM 错误时返回兜底文案，必须能发现替身没有被调用。
    assert checkin.json()["ai_feedback"] == SMOKE_FEEDBACK, "smoke LLM feedback missing"

    # 陪练面：历史读取可用（流式协议由陪练协议工单的测试覆盖）
    history = await smoke_client.get(f"/api/coach/{user_id}/history", headers=headers)
    assert history.status_code == 200, history.text

    # 越权：别人的资源不能被读到
    other = await smoke_client.get(f"/api/weight/{user_id + 1}/trend", headers=headers)
    assert other.status_code in (403, 404)


@pytest.mark.asyncio
async def test_main_path_smoke(smoke_client: AsyncClient):
    await run_main_path(smoke_client)


@pytest.mark.asyncio
async def test_main_path_smoke_detects_external_failure(smoke_client: AsyncClient, monkeypatch):
    """运行完全相同的旅程；工厂失败必须使成功路径断言变红，不能被 200 兜底掩盖。"""
    calls = 0

    async def broken_get_client(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("deliberate offline LLM failure")

    monkeypatch.setattr(LLMClientFactory, "get_client", broken_get_client)
    with pytest.raises(AssertionError, match="smoke LLM feedback missing"):
        await run_main_path(smoke_client)
    assert calls == 1, "故障替身必须实际被主链路触达"
