"""健康检查契约：存活不碰依赖，就绪逐项探测、独立超时、失败日志限流。

就绪检查是「这个实例现在能不能接流量」的唯一事实来源：必需依赖不可用时必须返回
503 让编排系统摘流量，而不是永远返回 ok。断言只看路由对外可观测面（状态码、逐项
字段、日志事件字段），不断言探测实现的内部结构。
"""

import asyncio
import json
import logging
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import health
from app.core.config import settings
from app.core.logging import StructuredJsonFormatter
from app.core.request_context import REQUEST_ID_HEADER
from app.main import app


@pytest.fixture(autouse=True)
def capture_logs(caplog):
    """Capture application logs and isolate probe throttle state between tests."""
    caplog.set_level(logging.INFO)
    health.reset_probe_log_throttle()
    try:
        yield caplog
    finally:
        health.reset_probe_log_throttle()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://health.test",
    ) as async_client:
        yield async_client


def stub_probe(monkeypatch, name: str, *, error: BaseException | None = None, delay: float = 0.0):
    """Replace one dependency probe and count how often it is consulted."""
    calls = {"count": 0}

    async def probe() -> None:
        calls["count"] += 1
        if delay:
            await asyncio.sleep(delay)
        if error is not None:
            raise error

    monkeypatch.setattr(health, name, probe)
    return calls


def _payloads(caplog) -> list[dict]:
    formatter = StructuredJsonFormatter()
    payloads = []
    for record in caplog.records:
        if getattr(record, "fields", None) is None:
            continue
        payloads.append(json.loads(formatter.format(record)))
    return payloads


def _dependency_events(caplog, event: str) -> list[dict]:
    return [payload for payload in _payloads(caplog) if payload.get("event") == event]


def _dependencies(body: dict) -> dict[str, dict]:
    return {item["name"]: item for item in body["dependencies"]}


@pytest.mark.asyncio
async def test_ready_reports_each_dependency_when_everything_is_healthy(monkeypatch, client):
    stub_probe(monkeypatch, "probe_database")
    stub_probe(monkeypatch, "probe_object_storage")
    stub_probe(monkeypatch, "probe_redis")

    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == app.version
    datetime.fromisoformat(body["started_at"])
    assert body["uptime_seconds"] >= 0

    dependencies = _dependencies(body)
    assert {"database", "object_storage", "redis"} <= set(dependencies)
    assert dependencies["database"]["required"] is True
    assert dependencies["object_storage"]["required"] is True
    assert dependencies["redis"]["required"] is False
    for item in dependencies.values():
        assert item["status"] == "ok"
        assert isinstance(item["latency_ms"], (int, float))
        assert item["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_ready_fails_when_database_is_unavailable(monkeypatch, client):
    stub_probe(monkeypatch, "probe_database", error=RuntimeError("database down"))
    stub_probe(monkeypatch, "probe_object_storage")
    stub_probe(monkeypatch, "probe_redis")

    response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    dependencies = _dependencies(body)
    assert dependencies["database"]["status"] == "fail"
    assert dependencies["database"]["error_code"]
    assert dependencies["object_storage"]["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_fails_when_object_storage_is_unavailable_but_database_stays_ok(
    monkeypatch, client
):
    stub_probe(monkeypatch, "probe_database")
    stub_probe(monkeypatch, "probe_object_storage", error=RuntimeError("minio down"))
    stub_probe(monkeypatch, "probe_redis")

    response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    dependencies = _dependencies(body)
    assert dependencies["object_storage"]["status"] == "fail"
    assert dependencies["database"]["status"] == "ok"


@pytest.mark.asyncio
async def test_optional_dependency_failure_degrades_without_failing_readiness(
    monkeypatch, client
):
    stub_probe(monkeypatch, "probe_database")
    stub_probe(monkeypatch, "probe_object_storage")
    stub_probe(monkeypatch, "probe_redis", error=RuntimeError("redis down"))

    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    dependencies = _dependencies(body)
    assert dependencies["redis"]["status"] == "fail"
    assert dependencies["redis"]["required"] is False
    assert dependencies["database"]["status"] == "ok"


@pytest.mark.asyncio
async def test_hanging_probe_is_bounded_by_its_own_timeout(monkeypatch, client):
    monkeypatch.setattr(settings, "HEALTH_PROBE_TIMEOUT_SECONDS", 0.05)
    stub_probe(monkeypatch, "probe_database")
    stub_probe(monkeypatch, "probe_object_storage", delay=5.0)
    stub_probe(monkeypatch, "probe_redis")

    started = asyncio.get_running_loop().time()
    response = await client.get("/health/ready")
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 2.0, "one hanging dependency must not stall the whole probe"
    assert response.status_code == 503
    dependencies = _dependencies(response.json())
    assert dependencies["object_storage"]["status"] == "fail"
    assert dependencies["object_storage"]["error_code"] == health.ERROR_CODE_PROBE_TIMEOUT
    assert dependencies["database"]["status"] == "ok"


@pytest.mark.asyncio
async def test_liveness_never_touches_dependencies(monkeypatch, client):
    database_calls = stub_probe(monkeypatch, "probe_database", error=RuntimeError("down"))
    storage_calls = stub_probe(monkeypatch, "probe_object_storage", error=RuntimeError("down"))
    redis_calls = stub_probe(monkeypatch, "probe_redis", error=RuntimeError("down"))

    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == app.version
    datetime.fromisoformat(body["started_at"])
    assert "dependencies" not in body
    assert database_calls["count"] == 0
    assert storage_calls["count"] == 0
    assert redis_calls["count"] == 0


@pytest.mark.asyncio
async def test_recovery_is_announced_once_after_a_failure_window(monkeypatch, client, caplog):
    state = {"failing": True}

    async def flaky_database() -> None:
        if state["failing"]:
            raise RuntimeError("database down")

    monkeypatch.setattr(health, "probe_database", flaky_database)
    stub_probe(monkeypatch, "probe_object_storage")
    stub_probe(monkeypatch, "probe_redis")

    assert (await client.get("/health/ready")).status_code == 503
    state["failing"] = False
    assert (await client.get("/health/ready")).status_code == 200

    recovered = _dependency_events(caplog, health.EVENT_DEPENDENCY_RECOVERED)
    assert [event["dependency"] for event in recovered] == ["database"]


@pytest.mark.asyncio
async def test_repeated_probe_failures_are_logged_once_per_window(monkeypatch, client, caplog):
    stub_probe(monkeypatch, "probe_database", error=RuntimeError("database down"))
    stub_probe(monkeypatch, "probe_object_storage")
    stub_probe(monkeypatch, "probe_redis")

    request_ids: list[str] = []
    for _ in range(5):
        response = await client.get("/health/ready")
        assert response.status_code == 503
        request_ids.append(response.headers[REQUEST_ID_HEADER])

    events = _dependency_events(caplog, health.EVENT_DEPENDENCY_FAILED)
    database_events = [event for event in events if event.get("dependency") == "database"]
    assert len(database_events) == 1, "repeated probe failures must be throttled"
    event = database_events[0]
    assert event["request_id"] in request_ids
    assert event["error_code"]
    assert event["level"] in {"warning", "error"}


@pytest.mark.asyncio
async def test_unavailable_readiness_does_not_log_an_error_completion(monkeypatch, client, caplog):
    """A 503 from the probe is an expected conclusion, not an unhandled failure."""
    stub_probe(monkeypatch, "probe_database", error=RuntimeError("database down"))
    stub_probe(monkeypatch, "probe_object_storage")
    stub_probe(monkeypatch, "probe_redis")

    response = await client.get("/health/ready")

    assert response.status_code == 503
    completions = [
        event
        for event in _payloads(caplog)
        if event.get("event") == "http.request.completed"
        and event.get("route") == "/health/ready"
    ]
    assert completions
    assert completions[-1]["status_code"] == 503
    assert completions[-1]["level"] == "warning"


@pytest.mark.asyncio
async def test_redis_is_not_probed_unless_this_deployment_enables_it(monkeypatch, client):
    """The URL has a local default; only an explicit opt-in probes Redis."""
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(settings, "REDIS_PROBE_ENABLED", False)
    stub_probe(monkeypatch, "probe_database")
    stub_probe(monkeypatch, "probe_object_storage")

    def forbidden_client(*args, **kwargs):
        raise AssertionError("redis must not be probed when the deployment does not use it")

    monkeypatch.setattr(redis_asyncio, "from_url", forbidden_client)

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    dependencies = _dependencies(response.json())
    assert dependencies["redis"]["status"] == "ok"
