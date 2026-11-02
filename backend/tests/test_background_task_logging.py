"""Background analysis task events: identity fields and inherited request id."""

import datetime
import json
import logging
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import vision as vision_api
from app.core.database import Base
from app.core.logging import StructuredJsonFormatter
from app.core.request_context import bind_request_context
from app.core.storage import InMemoryStorage
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
from app.models.user import User
from app.schemas.vision import AnalyzeRequest, BodyAnalysisResult


class _FailingVisionGraph:
    """Simulate an upstream analysis failure inside the background task."""

    def __init__(self, user_id: int, db) -> None:
        self.user_id = user_id
        self.db = db

    async def run(self, image_base64: str, profile=None):
        raise RuntimeError("provider exploded")


class _SuccessfulVisionGraph:
    """Return a minimal valid analysis result."""

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


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Isolated database so background-task writes are real persistence."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'background-tasks.db').as_posix()}",
        future=True,
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_user(session_factory):
    async with session_factory() as session:
        user = User(openid="background-task-user", nickname="Background")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _persisted_task(session_factory, task_id: str) -> AnalysisTask:
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task is not None
        return task


@pytest.fixture(autouse=True)
def capture_application_logs(caplog):
    caplog.set_level(logging.INFO)
    return caplog


def _payloads(caplog) -> list[dict]:
    formatter = StructuredJsonFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if getattr(record, "fields", None) is not None
    ]


@pytest.mark.asyncio
async def test_task_creation_logs_identity_and_captures_request_id(
    monkeypatch, caplog, session_factory, seeded_user
):
    created_coroutines: list = []

    def _fake_create_task(coroutine):
        coroutine.close()
        created_coroutines.append(coroutine)
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        vision_api, "asyncio", types.SimpleNamespace(create_task=_fake_create_task)
    )
    request = AnalyzeRequest(image_base64="abc", user_id=seeded_user.id)

    async with session_factory() as session:
        with bind_request_context(request_id="req-created-123456", user_id=seeded_user.id):
            response = await vision_api.start_analyze(
                request,
                db=session,
                current_user=SimpleNamespace(id=seeded_user.id),
                storage=InMemoryStorage(),
            )

    assert created_coroutines, "the background task should be scheduled"
    assert response.status == "pending"
    assert not response.task_id.isdigit(), "task ids must not be guessable integers"

    task = await _persisted_task(session_factory, response.task_id)
    assert task.status == "pending"
    assert task.attempt == 0
    assert task.request_id == "req-created-123456"
    assert task.expires_at is not None

    created = [
        payload
        for payload in _payloads(caplog)
        if payload.get("task_id") == response.task_id
    ]
    assert created, "expected a task creation event"
    event = created[0]
    assert event["request_id"] == "req-created-123456"
    assert event["user_id"] == seeded_user.id
    assert event["level"] == "info"


@pytest.mark.asyncio
async def test_task_failure_logs_error_with_task_context(
    monkeypatch, caplog, session_factory, seeded_user
):
    monkeypatch.setattr(vision_api, "VisionGraph", _FailingVisionGraph)
    monkeypatch.setattr(vision_api, "AsyncSessionLocal", session_factory)

    task_id = "task-failure-1"
    async with session_factory() as session:
        session.add(
            AnalysisTask(
                task_id=task_id,
                user_id=seeded_user.id,
                status="pending",
                stage="queued",
                attempt=0,
                progress=0,
                request_id="req-origin-abcdef12",
                input_image_base64="abc",
                expires_at=datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=10),
            )
        )
        await session.commit()

    await vision_api._run_analysis(
        task_id,
        AnalyzeRequest(image_base64="abc", user_id=seeded_user.id),
    )

    task = await _persisted_task(session_factory, task_id)
    assert task.status == "failed"
    assert task.error_code
    assert task.error_message

    failed = [
        payload
        for payload in _payloads(caplog)
        if payload.get("task_id") == task_id and payload.get("level") == "error"
    ]
    assert failed, "expected an error-level task failure event"
    event = failed[-1]
    assert event["user_id"] == seeded_user.id
    assert event["attempt"] == 1
    assert event["request_id"] == "req-origin-abcdef12"
    assert event["error_code"]
    assert event["error_class"] == "RuntimeError"
    assert "Traceback" in event["stack"]


@pytest.mark.asyncio
async def test_task_completion_logs_identity_and_duration(
    monkeypatch, caplog, session_factory, seeded_user
):
    monkeypatch.setattr(vision_api, "VisionGraph", _SuccessfulVisionGraph)
    monkeypatch.setattr(vision_api, "AsyncSessionLocal", session_factory)

    task_id = "task-success-1"
    async with session_factory() as session:
        session.add(
            AnalysisTask(
                task_id=task_id,
                user_id=seeded_user.id,
                status="pending",
                stage="queued",
                attempt=0,
                progress=0,
                request_id="req-origin-abcdef12",
                input_image_base64="abc",
                expires_at=datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=10),
            )
        )
        await session.commit()

    await vision_api._run_analysis(
        task_id,
        AnalyzeRequest(image_base64="abc", user_id=seeded_user.id),
    )

    task = await _persisted_task(session_factory, task_id)
    assert task.status == "completed"
    assert task.result
    assert task.history_record_id is not None

    async with session_factory() as session:
        history_count = await session.scalar(
            select(func.count()).select_from(BodyAnalysisRecord)
        )
    assert history_count == 1

    completed = [
        payload
        for payload in _payloads(caplog)
        if payload.get("task_id") == task_id and payload.get("level") == "info"
    ]
    assert completed, "expected an info-level task completion event"
    event = completed[-1]
    assert event["request_id"] == "req-origin-abcdef12"
    assert event["user_id"] == seeded_user.id
    assert event["attempt"] == 1
    assert event["duration_ms"] >= 0
