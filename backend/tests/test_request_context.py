"""Request correlation contract: response header, completion events, error records."""

import json
import logging
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import APIRouter
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.logging import StructuredJsonFormatter
from app.core.request_context import REQUEST_ID_HEADER, is_valid_request_id
from app.main import app
from app.models.user import User

_TEST_ROUTE_PREFIX = "/__test-observability"


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated SQLite database for request context tests."""
    db_path = tmp_path / "request-context.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_users(session_factory):
    """Seed a single normal user for authenticated request tests."""
    async with session_factory() as session:
        user = User(openid="request-context-user", nickname="User One", is_admin=False)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return {"normal": user}


@pytest_asyncio.fixture
async def client(session_factory):
    """Create an app client backed by the isolated test database."""

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
def failing_route():
    """Temporarily register a route that raises an unexpected exception."""
    router = APIRouter()

    @router.get(f"{_TEST_ROUTE_PREFIX}/boom")
    async def boom():
        raise RuntimeError("unexpected-secret-marker")

    app.include_router(router)
    try:
        yield
    finally:
        app.router.routes[:] = [
            route
            for route in app.router.routes
            if not getattr(route, "path", "").startswith(_TEST_ROUTE_PREFIX)
        ]


@pytest.fixture(autouse=True)
def capture_application_logs(caplog):
    """Capture application logger output for every test in this module."""
    caplog.set_level(logging.INFO)
    return caplog


def _auth_headers(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _payloads(caplog) -> list[dict]:
    """Serialize every structured record with the production formatter."""
    formatter = StructuredJsonFormatter()
    payloads = []
    for record in caplog.records:
        if getattr(record, "fields", None) is None:
            continue
        payloads.append(json.loads(formatter.format(record)))
    return payloads


def _route_events(caplog, route: str, method: str = "GET") -> list[dict]:
    return [
        payload
        for payload in _payloads(caplog)
        if payload.get("route") == route and payload.get("method") == method
    ]


@pytest.mark.asyncio
async def test_response_header_carries_a_generated_request_id(client):
    response = await client.get("/health")

    assert response.status_code == 200
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id
    assert is_valid_request_id(request_id)


@pytest.mark.asyncio
async def test_valid_inbound_request_id_is_reused(client):
    supplied = "0123456789abcdef0123456789abcdef"

    response = await client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    assert response.headers[REQUEST_ID_HEADER] == supplied


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "supplied",
    [
        "short",
        "bad id with spaces",
        "<script>alert(1)</script>",
        "a" * 200,
    ],
)
async def test_invalid_inbound_request_id_is_replaced(client, supplied):
    response = await client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != supplied
    assert is_valid_request_id(returned)


@pytest.mark.asyncio
async def test_completion_event_has_request_fields_and_single_line_output(client, caplog):
    response = await client.get("/health")

    events = _route_events(caplog, "/health")
    assert events, "expected a completion event for the health route"
    event = events[-1]
    assert event["status_code"] == 200
    assert event["duration_ms"] >= 0
    assert event["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert event["user_id"] is None
    assert event["level"] == "info"


@pytest.mark.asyncio
async def test_route_field_uses_template_not_path_values(client, caplog):
    response = await client.get("/api/user/987654")

    assert response.status_code == 401
    events = [
        payload
        for payload in _payloads(caplog)
        if payload.get("method") == "GET" and payload.get("status_code") == 401
    ]
    assert events
    event = events[-1]
    assert event["route"] == "/api/user/{user_id}"
    assert "987654" not in json.dumps(event, ensure_ascii=False)


@pytest.mark.asyncio
async def test_authenticated_user_is_recorded_on_the_completion_event(
    client, seeded_users, caplog
):
    user = seeded_users["normal"]

    response = await client.get("/api/user/me", headers=_auth_headers(user.id))

    assert response.status_code == 200
    events = _route_events(caplog, "/api/user/me")
    assert events
    assert events[-1]["user_id"] == user.id


@pytest.mark.asyncio
async def test_business_4xx_is_warning_without_stack(client, caplog):
    response = await client.get("/api/user/me")

    assert response.status_code == 401
    assert response.headers.get(REQUEST_ID_HEADER)
    events = _route_events(caplog, "/api/user/me")
    assert events
    event = events[-1]
    assert event["level"] == "warning"
    assert event["status_code"] == 401
    assert event["error_code"]
    assert "stack" not in event


def test_unhandled_exception_returns_stable_error_and_logs_stack(failing_route, caplog):
    caplog.set_level(logging.INFO)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(f"{_TEST_ROUTE_PREFIX}/boom")

    assert response.status_code == 500
    assert response.json() == {"code": 500, "message": "服务器内部错误，请稍后重试"}
    assert "unexpected-secret-marker" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text

    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id
    assert is_valid_request_id(request_id)

    error_events = [
        payload for payload in _payloads(caplog) if payload.get("level") == "error"
    ]
    assert error_events, "expected an error-level event for the unhandled exception"
    event = error_events[-1]
    assert event["request_id"] == request_id
    assert event["status_code"] == 500
    assert "Traceback" in event["stack"]
    assert event["error_class"] == "RuntimeError"


@pytest.mark.asyncio
async def test_cors_exposes_the_request_id_header(client):
    response = await client.get("/health", headers={"Origin": "http://localhost:5173"})

    exposed = response.headers.get("access-control-expose-headers", "")
    assert REQUEST_ID_HEADER.lower() in exposed.lower()
