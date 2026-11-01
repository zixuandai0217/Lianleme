"""Route-level contract for durable body-analysis task creation and polling.

These tests exercise the real FastAPI routes and the real persistence layer,
replacing only the background execution entry point.  They assert externally
observable behavior (HTTP status, response fields, persisted task/history rows),
never the shape of an in-process task store.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import vision as vision_api
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
from app.models.user import User
from app.schemas.vision import AnalyzeRequest, BodyAnalysisResult
from app.services.user.api_key_service import ApiKeyService

NOW = datetime.datetime.now(datetime.timezone.utc)


class _SuccessfulVisionGraph:
    def __init__(self, user_id: int, db) -> None:
        self.user_id = user_id
        self.db = db

    async def run(self, image_base64: str, profile=None) -> BodyAnalysisResult:
        return BodyAnalysisResult(
            body_type="mesomorph",
            body_fat_range="15-20%",
            weak_muscles=["背"],
            strengths=["腿"],
            muscle_scores={"back": 6},
            summary="保持训练",
        )


class _TimeoutVisionGraph:
    def __init__(self, user_id: int, db) -> None:
        self.user_id = user_id
        self.db = db

    async def run(self, image_base64: str, profile=None):
        raise RuntimeError("provider timeout 504 upstream-secret")


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'analysis-tasks.db').as_posix()}",
        future=True,
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    """A keyed user, another keyed user, and a keyless user."""
    async with session_factory() as session:
        keyed = User(openid="analysis-keyed", nickname="Keyed")
        other = User(openid="analysis-other", nickname="Other")
        keyless = User(openid="analysis-keyless", nickname="Keyless")
        session.add_all([keyed, other, keyless])
        await session.commit()
        await session.refresh(keyed)
        await session.refresh(other)
        await session.refresh(keyless)
        await ApiKeyService(session).save_key(keyed.id, "openai", "sk-keyed-1234567890")
        await ApiKeyService(session).save_key(other.id, "openai", "sk-other-1234567890")
        await session.commit()
        return {"keyed": keyed, "other": other, "keyless": keyless}


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
def stub_background(monkeypatch):
    """Keep HTTP tests deterministic while retaining the original entry point."""
    original = vision_api._run_analysis
    stub = AsyncMock()
    monkeypatch.setattr(vision_api, "_run_analysis", stub)
    return {"original": original, "stub": stub}


def auth_headers(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _task_count(session_factory) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(AnalysisTask)) or 0)


async def _history_count(session_factory) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(select(func.count()).select_from(BodyAnalysisRecord)) or 0
        )


async def _seed_task(session_factory, user_id: int, task_id: str, **overrides) -> None:
    values = {
        "task_id": task_id,
        "user_id": user_id,
        "status": "pending",
        "stage": "queued",
        "attempt": 0,
        "progress": 0,
        "expires_at": NOW + datetime.timedelta(minutes=10),
    }
    values.update(overrides)
    async with session_factory() as session:
        session.add(AnalysisTask(**values))
        await session.commit()


@pytest.mark.asyncio
async def test_create_task_persists_pending_record_with_unknown_id(
    client, session_factory, users, stub_background
):
    user = users["keyed"]

    response = await client.post(
        "/api/vision/analyze",
        json={"user_id": user.id, "image_base64": "aW1hZ2U="},
        headers=auth_headers(user.id),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "pending"
    assert body["stage"] == "queued"
    assert body["task_id"]
    assert not body["task_id"].isdigit(), "task id must not be a guessable integer"
    assert body["created_at"]
    assert body["expires_at"]
    assert body["poll_interval_ms"] >= 0

    second = await client.post(
        "/api/vision/analyze",
        json={"user_id": user.id, "image_base64": "aW1hZ2U="},
        headers=auth_headers(user.id),
    )
    assert second.status_code == 200
    assert second.json()["task_id"] != body["task_id"]

    assert await _task_count(session_factory) == 2
    assert await _history_count(session_factory) == 0

    async with session_factory() as session:
        task = await session.get(AnalysisTask, body["task_id"])
        assert task is not None
        assert task.user_id == user.id
        assert task.status == "pending"
        assert task.attempt == 0
        assert task.expires_at is not None
        expires_at = task.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        assert expires_at > NOW


@pytest.mark.asyncio
async def test_keyless_user_gets_428_and_no_task_is_created(
    client, session_factory, users
):
    user = users["keyless"]

    response = await client.post(
        "/api/vision/analyze",
        json={"user_id": user.id, "image_base64": "aW1hZ2U="},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 428
    assert response.json()["detail"]["code"] == "api_key_required"
    assert await _task_count(session_factory) == 0
    assert await _history_count(session_factory) == 0


@pytest.mark.asyncio
async def test_new_task_is_immediately_pollable(client, users):
    user = users["keyed"]
    created = await client.post(
        "/api/vision/analyze",
        json={"user_id": user.id, "image_base64": "aW1hZ2U="},
        headers=auth_headers(user.id),
    )
    task_id = created.json()["task_id"]

    response = await client.get(
        f"/api/vision/analyze/{task_id}",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["task_id"] == task_id
    assert body["status"] in {"pending", "processing"}
    assert body["attempt"] in {0, 1}
    assert body["result"] is None
    assert body["error"] is None
    assert body["created_at"]
    assert body["updated_at"]
    assert body["expires_at"]


@pytest.mark.asyncio
async def test_task_survives_process_restart_and_completes_with_history(
    client, session_factory, users, stub_background, monkeypatch
):
    user = users["keyed"]
    created = await client.post(
        "/api/vision/analyze",
        json={"user_id": user.id, "image_base64": "aW1hZ2U="},
        headers=auth_headers(user.id),
    )
    task_id = created.json()["task_id"]

    # Simulate a fresh process: only the database remains, and the executor is
    # invoked explicitly against that persisted record.
    monkeypatch.setattr(vision_api, "_run_analysis", stub_background["original"])
    monkeypatch.setattr(vision_api, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(vision_api, "VisionGraph", _SuccessfulVisionGraph)

    await stub_background["original"](
        task_id,
        AnalyzeRequest(user_id=user.id, image_base64="aW1hZ2U="),
    )

    response = await client.get(
        f"/api/vision/analyze/{task_id}",
        headers=auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["stage"] == "done"
    assert body["attempt"] == 1
    assert body["progress"] == 100
    assert body["error"] is None
    assert body["result"]["body_type"] == "mesomorph"

    history = await client.get(
        f"/api/vision/{user.id}/history",
        headers=auth_headers(user.id),
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1

    # Polling is read-only and idempotent: no duplicate execution or history.
    second = await client.get(
        f"/api/vision/analyze/{task_id}",
        headers=auth_headers(user.id),
    )
    assert second.status_code == 200
    assert second.json() == body
    assert await _history_count(session_factory) == 1


@pytest.mark.asyncio
async def test_failed_task_returns_stable_safe_error_and_no_history(
    client, session_factory, users, stub_background, monkeypatch
):
    user = users["keyed"]
    created = await client.post(
        "/api/vision/analyze",
        json={"user_id": user.id, "image_base64": "aW1hZ2U="},
        headers=auth_headers(user.id),
    )
    task_id = created.json()["task_id"]

    monkeypatch.setattr(vision_api, "_run_analysis", stub_background["original"])
    monkeypatch.setattr(vision_api, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(vision_api, "VisionGraph", _TimeoutVisionGraph)

    await stub_background["original"](
        task_id,
        AnalyzeRequest(user_id=user.id, image_base64="aW1hZ2U="),
    )

    response = await client.get(
        f"/api/vision/analyze/{task_id}",
        headers=auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"]["code"] == "provider_timeout"
    assert body["error"]["retryable"] is True
    assert "upstream-secret" not in response.text
    assert "504" not in response.text
    assert await _history_count(session_factory) == 0


@pytest.mark.asyncio
async def test_expired_task_returns_200_expired_not_404(client, session_factory, users):
    user = users["keyed"]
    task_id = "expired-task-1"
    await _seed_task(
        session_factory,
        user.id,
        task_id,
        expires_at=NOW - datetime.timedelta(seconds=1),
    )

    response = await client.get(
        f"/api/vision/analyze/{task_id}",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "expired"
    assert body["result"] is None
    assert body["error"]["code"] == "task_expired"
    assert body["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_unknown_task_returns_404_with_task_not_found_code(client, users):
    user = users["keyed"]

    response = await client.get(
        "/api/vision/analyze/does-not-exist",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "task_not_found"


@pytest.mark.asyncio
async def test_other_users_task_is_forbidden_and_leaks_nothing(
    client, session_factory, users
):
    owner = users["keyed"]
    stranger = users["other"]
    task_id = "private-task-1"
    await _seed_task(
        session_factory,
        owner.id,
        task_id,
        status="completed",
        stage="done",
        attempt=1,
        progress=100,
        result=BodyAnalysisResult(
            body_type="ectomorph",
            body_fat_range="10-12%",
            weak_muscles=["胸"],
            strengths=["背"],
            muscle_scores={"chest": 4},
            summary="私密结果",
        ).model_dump(),
    )

    response = await client.get(
        f"/api/vision/analyze/{task_id}",
        headers=auth_headers(stranger.id),
    )

    assert response.status_code == 403
    assert "ectomorph" not in response.text
    assert "私密结果" not in response.text
    assert "body_type" not in response.text


@pytest.mark.asyncio
async def test_failed_task_fields_are_complete_and_mutually_exclusive(
    client, session_factory, users
):
    user = users["keyed"]
    task_id = "failed-task-1"
    await _seed_task(
        session_factory,
        user.id,
        task_id,
        status="failed",
        stage="done",
        attempt=2,
        error_code="provider_auth_failed",
        error_message="AI 服务鉴权失败，请检查 API Key 配置后重试",
        error_retryable=False,
    )

    response = await client.get(
        f"/api/vision/analyze/{task_id}",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["attempt"] == 2
    assert body["result"] is None
    assert body["error"] == {
        "code": "provider_auth_failed",
        "message": "AI 服务鉴权失败，请检查 API Key 配置后重试",
        "retryable": False,
    }


@pytest.mark.asyncio
async def test_database_write_failure_returns_5xx_without_task_id(
    client, session_factory, users
):
    user = users["keyed"]

    async def failing_commit_override():
        async with session_factory() as session:
            async def _boom() -> None:
                raise RuntimeError("database unavailable")

            session.commit = _boom  # type: ignore[method-assign]
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = failing_commit_override
    try:
        response = await client.post(
            "/api/vision/analyze",
            json={"user_id": user.id, "image_base64": "aW1hZ2U="},
            headers=auth_headers(user.id),
        )
    finally:
        app.dependency_overrides[get_db] = previous

    assert response.status_code >= 500
    assert "task_id" not in response.json()
    assert await _task_count(session_factory) == 0
