"""SSE lifecycle observability: stream start, normal end, client drop, upstream failure."""

import json
import logging
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from app.api import coach as coach_api
from app.core.database import get_db
from app.core.logging import StructuredJsonFormatter
from app.core.observability import RequestContextMiddleware
from app.core.request_context import REQUEST_ID_HEADER, is_valid_request_id
from app.core.security import require_current_user_api_key
from app.main import app

_TEST_ROUTE_PREFIX = "/__test-observability-sse"


@pytest.fixture
def sse_routes():
    """Register throwaway SSE routes that exercise each stream ending."""
    router = APIRouter()

    @router.get(f"{_TEST_ROUTE_PREFIX}/ok")
    async def stream_ok():
        async def generate():
            yield "data: one\n\n"
            yield "data: two\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @router.get(f"{_TEST_ROUTE_PREFIX}/fail")
    async def stream_fail():
        async def generate():
            yield "data: one\n\n"
            raise RuntimeError("provider exploded")

        return StreamingResponse(generate(), media_type="text/event-stream")

    app.include_router(router)
    try:
        yield
    finally:
        app.router.routes[:] = [
            route
            for route in app.router.routes
            if not getattr(route, "path", "").startswith(_TEST_ROUTE_PREFIX)
        ]


@pytest_asyncio.fixture
async def client(sse_routes):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client


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
async def test_normal_stream_logs_start_and_completion(client, caplog):
    response = await client.get(f"{_TEST_ROUTE_PREFIX}/ok")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert is_valid_request_id(request_id)

    payloads = _payloads(caplog)
    started = [payload for payload in payloads if payload["event"] == "stream.sse.started"]
    completed = [payload for payload in payloads if payload["event"] == "stream.sse.completed"]
    assert started, "expected a stream start event"
    assert completed, "expected a stream completion event"
    assert started[-1]["request_id"] == request_id
    assert completed[-1]["request_id"] == request_id
    assert completed[-1]["level"] == "info"
    assert completed[-1]["chunks_sent"] >= 2
    assert completed[-1]["bytes_sent"] == len("data: one\n\ndata: two\n\n")


@pytest.mark.asyncio
async def test_upstream_failure_logs_warning_with_error_class(client, caplog):
    # Starlette wraps a failed body iterator in an ExceptionGroup; either shape is
    # fine, the contract under test is the failure event that gets written.
    with pytest.raises(BaseException):
        await client.get(f"{_TEST_ROUTE_PREFIX}/fail")

    payloads = _payloads(caplog)
    failed = [payload for payload in payloads if payload["event"] == "stream.sse.failed"]
    assert failed, "expected a stream failure event"
    event = failed[-1]
    assert event["level"] == "warning"
    assert event["error_class"] == "RuntimeError"
    assert event["error_code"]
    assert event["chunks_sent"] == 1


@pytest.mark.asyncio
async def test_client_interruption_logs_warning(caplog):
    """A stream that ends without a final frame models a dropped client connection."""

    async def dropping_app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"data: one\n\n",
                "more_body": True,
            }
        )
        # Returning without a final (more_body=False) frame means the client went away.

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = RequestContextMiddleware(dropping_app)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 4444),
        "server": ("testserver", 80),
    }
    await middleware(scope, receive, send)

    payloads = _payloads(caplog)
    interrupted = [
        payload for payload in payloads if payload["event"] == "stream.sse.interrupted"
    ]
    assert interrupted, "expected a stream interruption event"
    event = interrupted[-1]
    assert event["level"] == "warning"
    assert event["error_code"]
    assert event["chunks_sent"] == 1
    assert sent and sent[-1]["type"] == "http.response.body"


COACH_STREAM_URL = "/api/coach/chat/stream"


class _FailingCoachGraph:
    """Raise the same class of failure produced by an invalid provider key."""

    def __init__(self, user_id: int, db: object) -> None:
        self.user_id = user_id
        self.db = db

    async def stream_chat(self, message: str, context: dict):
        if False:
            yield ""
        raise RuntimeError("invalid provider key")

    async def save_turn(self, message: str, reply: str) -> None:
        raise AssertionError("a failed turn must not be persisted")


@pytest.mark.asyncio
async def test_coach_stream_upstream_failure_ends_with_warning_event(monkeypatch, caplog):
    """The coach route turns a provider failure into a frame; the event must stay a failure."""
    monkeypatch.setattr(coach_api, "CoachGraph", _FailingCoachGraph)

    async def override_get_db():
        yield object()

    async def override_current_user():
        return SimpleNamespace(id=7)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_current_user_api_key] = override_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                COACH_STREAM_URL,
                json={"user_id": 7, "message": "hello"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    failed = [
        payload for payload in _payloads(caplog) if payload["event"] == "stream.sse.failed"
    ]
    assert failed, "a swallowed upstream failure must still end with a warning event"
    event = failed[-1]
    assert event["level"] == "warning"
    assert event["request_id"] == request_id
    assert event["route"] == COACH_STREAM_URL
    assert event["error_code"] in {
        "provider_unavailable",
        "rate_limited",
        "upstream_timeout",
        "internal",
    }
    assert event["error_class"] == "RuntimeError"
