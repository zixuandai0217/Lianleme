"""Liveness and readiness probes.

Liveness answers "is the process alive" and must never touch an external
dependency: a flapping dependency would otherwise make the orchestrator restart a
healthy process. Readiness answers "can this instance take traffic": it probes
every dependency with its own short timeout and reports per-dependency status, so
a missing dependency takes traffic away instead of silently accepting requests.

Probe failures are frequent by nature (a broken dependency fails every probe), so
failure logging is throttled per dependency. Both formats carry the request
identifier through the structured logging context.
"""

import asyncio
import datetime
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import (
    EVENT_DEPENDENCY_FAILED,
    EVENT_DEPENDENCY_RECOVERED,
    FIELD_DEPENDENCY,
    FIELD_DURATION_MS,
    FIELD_ERROR_CODE,
    log_event,
)

logger = logging.getLogger("app.health")

# Single source of truth for the version shown by both probes and FastAPI.
APP_VERSION = "0.1.0"

# Aggregated readiness states (spec §8).
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_UNAVAILABLE = "unavailable"

# Per-dependency failure codes: a timeout is distinguishable from a hard failure,
# because "the dependency is unreachable" and "the dependency is too slow" lead to
# different runbooks.
ERROR_CODE_PROBE_TIMEOUT = "timeout"
ERROR_CODE_PROBE_FAILED = "unavailable"

_STARTED_AT = datetime.datetime.now(datetime.timezone.utc)

# Last time a dependency's failure was logged, in monotonic seconds.
_FAILURE_LOGGED_AT: dict[str, float] = {}


def reset_probe_log_throttle() -> None:
    """Forget throttling state (used by tests and an explicit config reload)."""
    _FAILURE_LOGGED_AT.clear()


@dataclass(frozen=True)
class Dependency:
    """One probeable dependency; only required ones can fail readiness."""

    name: str
    required: bool
    probe: Callable[[], Awaitable[None]]


def dependencies() -> tuple[Dependency, ...]:
    """Return the dependencies to probe, resolved at call time.

    Built per call (not at import) so tests can replace a single probe without
    monkeypatching the whole registry.
    """
    return (
        Dependency("database", True, probe_database),
        Dependency("object_storage", True, probe_object_storage),
        Dependency("redis", False, probe_redis),
    )


async def probe_database() -> None:
    """Run the cheapest possible query so a dead pool fails fast."""
    from app.core.database import engine

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def probe_object_storage() -> None:
    """Check that the configured bucket exists; the MinIO call is blocking."""
    from app.core.storage import bounded_minio_client

    timeout = float(settings.HEALTH_PROBE_TIMEOUT_SECONDS)
    with bounded_minio_client(timeout) as client:
        exists = await asyncio.to_thread(client.bucket_exists, settings.MINIO_BUCKET)
    if not exists:
        raise RuntimeError(f"bucket missing: {settings.MINIO_BUCKET}")


async def probe_redis() -> None:
    """Ping the optional Redis instance only when this deployment uses Redis.

    The URL has a local default, so "URL is set" cannot mean "Redis is used here";
    probing unconditionally would leave every Redis-less deployment permanently
    degraded and log a failure every throttle window.
    """
    if not settings.REDIS_PROBE_ENABLED or not settings.REDIS_URL.strip():
        return
    import redis.asyncio as redis_asyncio

    client = redis_asyncio.from_url(settings.REDIS_URL)
    try:
        await client.ping()
    finally:
        await client.aclose()


def _log_probe_failure(dependency: Dependency, *, error_code: str, latency_ms: float) -> None:
    """Log one failure per dependency per throttle window."""
    now = time.monotonic()
    interval = max(0.0, float(settings.HEALTH_PROBE_LOG_THROTTLE_SECONDS))
    last = _FAILURE_LOGGED_AT.get(dependency.name)
    if last is not None and now - last < interval:
        return
    _FAILURE_LOGGED_AT[dependency.name] = now
    log_event(
        logger,
        EVENT_DEPENDENCY_FAILED,
        message="依赖探测失败",
        level=logging.WARNING,
        **{
            FIELD_DEPENDENCY: dependency.name,
            FIELD_ERROR_CODE: error_code,
            FIELD_DURATION_MS: latency_ms,
        },
    )


def _log_probe_recovery(dependency: Dependency, *, latency_ms: float) -> None:
    """Announce recovery once, so a failure window has a visible end."""
    if _FAILURE_LOGGED_AT.pop(dependency.name, None) is None:
        return
    log_event(
        logger,
        EVENT_DEPENDENCY_RECOVERED,
        message="依赖探测恢复",
        level=logging.INFO,
        **{
            FIELD_DEPENDENCY: dependency.name,
            FIELD_DURATION_MS: latency_ms,
        },
    )


async def _run_probe(dependency: Dependency) -> dict[str, Any]:
    """Probe one dependency under its own timeout and describe the outcome."""
    started = time.perf_counter()
    error_code: str | None = None
    try:
        await asyncio.wait_for(
            dependency.probe(),
            timeout=float(settings.HEALTH_PROBE_TIMEOUT_SECONDS),
        )
    except (asyncio.TimeoutError, TimeoutError):
        error_code = ERROR_CODE_PROBE_TIMEOUT
    except Exception:
        error_code = ERROR_CODE_PROBE_FAILED
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    if error_code is None:
        _log_probe_recovery(dependency, latency_ms=latency_ms)
    else:
        _log_probe_failure(dependency, error_code=error_code, latency_ms=latency_ms)

    item: dict[str, Any] = {
        "name": dependency.name,
        "required": dependency.required,
        "status": "ok" if error_code is None else "fail",
        "latency_ms": latency_ms,
    }
    if error_code is not None:
        item["error_code"] = error_code
    return item


def _aggregate_status(items: list[dict[str, Any]]) -> str:
    if any(item["required"] and item["status"] == "fail" for item in items):
        return STATUS_UNAVAILABLE
    if any(item["status"] == "fail" for item in items):
        return STATUS_DEGRADED
    return STATUS_OK


async def build_readiness() -> tuple[dict[str, Any], int]:
    """Return the readiness report and the HTTP status the route should send."""
    items = list(await asyncio.gather(*(_run_probe(item) for item in dependencies())))
    status = _aggregate_status(items)
    uptime = (datetime.datetime.now(datetime.timezone.utc) - _STARTED_AT).total_seconds()
    report = {
        "status": status,
        "version": APP_VERSION,
        "started_at": _STARTED_AT.isoformat().replace("+00:00", "Z"),
        "uptime_seconds": int(uptime),
        "dependencies": items,
    }
    return report, 503 if status == STATUS_UNAVAILABLE else 200


def liveness_report() -> dict[str, Any]:
    """Return the liveness payload without touching any dependency."""
    return {
        "status": "ok",
        "service": "lianleme-api",
        "version": APP_VERSION,
        "started_at": _STARTED_AT.isoformat().replace("+00:00", "Z"),
    }
