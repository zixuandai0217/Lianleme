"""主链路冒烟：注册 → 登录 → 档案 → 体重 → 今日计划 → 陪练历史。

这条用例不依赖任何外部服务（不调 LLM、不连 MinIO），只验证路由接线与鉴权在端到端
路径上真的能串起来，是质量门完整档的最后一道自检。
"""

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app


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

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://smoke.test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_main_path_smoke(smoke_client: AsyncClient):
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

    # 陪练面：历史读取可用（流式协议由陪练协议工单的测试覆盖）
    history = await smoke_client.get(f"/api/coach/{user_id}/history", headers=headers)
    assert history.status_code == 200, history.text

    # 越权：别人的资源不能被读到
    other = await smoke_client.get(f"/api/weight/{user_id + 1}/trend", headers=headers)
    assert other.status_code in (403, 404)
