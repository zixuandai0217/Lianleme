"""Background analysis task events: identity fields and inherited request id."""

import json
import logging
import types
from types import SimpleNamespace

import pytest

from app.api import vision as vision_api
from app.core.logging import StructuredJsonFormatter
from app.core.request_context import bind_request_context
from app.schemas.vision import AnalyzeRequest, BodyAnalysisResult


class _DummySession:
    """Stand-in for the background task's database session."""

    def add(self, _obj) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False


def _dummy_session_factory():
    return _DummySession()


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


class _DummyUserService:
    def __init__(self, db) -> None:
        self.db = db

    async def save_body_analysis(self, user_id: int, payload: dict) -> None:
        return None


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
async def test_task_creation_logs_identity_and_captures_request_id(monkeypatch, caplog):
    created_coroutines: list = []

    def _fake_create_task(coroutine):
        coroutine.close()
        created_coroutines.append(coroutine)
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        vision_api, "asyncio", types.SimpleNamespace(create_task=_fake_create_task)
    )
    request = AnalyzeRequest(image_base64="abc", user_id=7)

    with bind_request_context(request_id="req-created-123456", user_id=7):
        response = await vision_api.start_analyze(
            request,
            db=object(),
            current_user=SimpleNamespace(id=7),
        )

    try:
        assert created_coroutines, "the background task should be scheduled"
        stored = vision_api._tasks[response.task_id]
        assert stored["request_id"] == "req-created-123456"

        created = [
            payload
            for payload in _payloads(caplog)
            if payload.get("task_id") == response.task_id
        ]
        assert created, "expected a task creation event"
        event = created[0]
        assert event["request_id"] == "req-created-123456"
        assert event["user_id"] == 7
        assert event["level"] == "info"
    finally:
        vision_api._tasks.pop(response.task_id, None)


@pytest.mark.asyncio
async def test_task_failure_logs_error_with_task_context(monkeypatch, caplog):
    monkeypatch.setattr(vision_api, "VisionGraph", _FailingVisionGraph)
    monkeypatch.setattr(vision_api, "AsyncSessionLocal", _dummy_session_factory)

    task_id = "task-failure-1"
    vision_api._tasks[task_id] = {
        "status": "processing",
        "result": None,
        "error": None,
        "user_id": 7,
        "request_id": "req-origin-abcdef12",
        "attempt": 1,
    }
    try:
        await vision_api._run_analysis(
            task_id,
            AnalyzeRequest(image_base64="abc", user_id=7),
        )
        assert vision_api._tasks[task_id]["status"] == "failed"
    finally:
        vision_api._tasks.pop(task_id, None)

    failed = [
        payload
        for payload in _payloads(caplog)
        if payload.get("task_id") == task_id and payload.get("level") == "error"
    ]
    assert failed, "expected an error-level task failure event"
    event = failed[-1]
    assert event["user_id"] == 7
    assert event["attempt"] == 1
    assert event["request_id"] == "req-origin-abcdef12"
    assert event["error_code"]
    assert event["error_class"] == "RuntimeError"
    assert "Traceback" in event["stack"]


@pytest.mark.asyncio
async def test_task_completion_logs_identity_and_duration(monkeypatch, caplog):
    monkeypatch.setattr(vision_api, "VisionGraph", _SuccessfulVisionGraph)
    monkeypatch.setattr(vision_api, "UserService", _DummyUserService)
    monkeypatch.setattr(vision_api, "AsyncSessionLocal", _dummy_session_factory)

    task_id = "task-success-1"
    vision_api._tasks[task_id] = {
        "status": "processing",
        "result": None,
        "error": None,
        "user_id": 7,
        "request_id": "req-origin-abcdef12",
        "attempt": 1,
    }
    try:
        await vision_api._run_analysis(
            task_id,
            AnalyzeRequest(image_base64="abc", user_id=7),
        )
        assert vision_api._tasks[task_id]["status"] == "completed"
    finally:
        vision_api._tasks.pop(task_id, None)

    completed = [
        payload
        for payload in _payloads(caplog)
        if payload.get("task_id") == task_id and payload.get("level") == "info"
    ]
    assert completed, "expected an info-level task completion event"
    event = completed[-1]
    assert event["request_id"] == "req-origin-abcdef12"
    assert event["user_id"] == 7
    assert event["attempt"] == 1
    assert event["duration_ms"] >= 0
