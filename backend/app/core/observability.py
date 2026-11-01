"""HTTP request correlation middleware and SSE lifecycle observability.

The middleware owns three responsibilities at the single highest seam:

* resolve or mint the request identifier and expose it on every response;
* emit one completion event per request (with a slow-request marker);
* emit start/end events for streaming responses, distinguishing a normal end, a
  client interruption and an upstream failure.

It stays out of the route handlers, so business code never passes identifiers
around by hand.
"""

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Any

from starlette.requests import ClientDisconnect

from app.core import request_context
from app.core.config import settings
from app.core.logging import (
    ERROR_CODE_CLIENT_DISCONNECT,
    ERROR_CODE_HTTP_PREFIX,
    ERROR_CODE_STREAM_FAILED,
    EVENT_HTTP_COMPLETED,
    EVENT_HTTP_SLOW,
    EVENT_SSE_COMPLETED,
    EVENT_SSE_FAILED,
    EVENT_SSE_INTERRUPTED,
    EVENT_SSE_STARTED,
    FIELD_BYTES_SENT,
    FIELD_CHUNKS_SENT,
    FIELD_DURATION_MS,
    FIELD_ERROR_CLASS,
    FIELD_ERROR_CODE,
    FIELD_METHOD,
    FIELD_ROUTE,
    FIELD_STATUS_CODE,
    log_event,
    root_cause,
)

logger = logging.getLogger("app.observability")

_SSE_CONTENT_TYPE = "text/event-stream"


def _header_value(scope: Mapping[str, Any], name: str) -> str | None:
    wanted = name.lower().encode("latin-1")
    for key, value in scope.get("headers", ()):  # type: ignore[union-attr]
        if key.lower() == wanted:
            return value.decode("latin-1")
    return None


def _content_type(headers: list[tuple[bytes, bytes]]) -> str:
    for key, value in headers:
        if key.lower() == b"content-type":
            return value.decode("latin-1")
    return ""


def route_template(scope: Mapping[str, Any]) -> str | None:
    """Return the matched route template without resolved path parameters."""
    route = scope.get("route")
    template = getattr(route, "path", None) or getattr(route, "path_format", None)
    return template


STREAM_ERROR_STATE_KEY = "stream_error"


def mark_stream_failed(scope: dict, *, error_code: str, error_class: str) -> None:
    """Flag an upstream failure that a streaming route converted into a frame.

    The middleware owns the end-of-stream event and the route owns the failure
    category, so the route records the category here and the middleware renders
    a warning end event instead of a clean completion.
    """
    scope.setdefault("state", {})[STREAM_ERROR_STATE_KEY] = {
        FIELD_ERROR_CODE: error_code,
        FIELD_ERROR_CLASS: error_class,
    }


def _stream_error(scope: Mapping[str, Any]) -> dict[str, Any] | None:
    state = scope.get("state") or {}
    value = state.get(STREAM_ERROR_STATE_KEY) if isinstance(state, Mapping) else None
    return value if isinstance(value, dict) else None


def _log_request_completed(
    scope: Mapping[str, Any],
    *,
    method: str,
    status_code: int | None,
    duration_ms: float,
) -> None:
    level = logging.INFO
    route = route_template(scope)
    fields: dict[str, Any] = {
        FIELD_METHOD: method,
        FIELD_ROUTE: route,
        FIELD_STATUS_CODE: status_code,
        FIELD_DURATION_MS: duration_ms,
    }
    if status_code is not None and status_code >= 400:
        fields[FIELD_ERROR_CODE] = f"{ERROR_CODE_HTTP_PREFIX}{status_code}"
        level = logging.ERROR if status_code >= 500 else logging.WARNING
    log_event(logger, EVENT_HTTP_COMPLETED, message="请求完成", level=level, **fields)

    if duration_ms >= settings.SLOW_REQUEST_THRESHOLD_MS:
        log_event(
            logger,
            EVENT_HTTP_SLOW,
            message="慢请求",
            level=logging.WARNING,
            method=method,
            route=route,
            status_code=status_code,
            duration_ms=duration_ms,
        )


def _log_stream_event(
    event: str,
    scope: Mapping[str, Any],
    *,
    method: str,
    stream: dict[str, Any],
    level: int,
    message: str,
    error_code: str | None = None,
    error_class: str | None = None,
) -> None:
    fields: dict[str, Any] = {
        FIELD_METHOD: method,
        FIELD_ROUTE: route_template(scope),
        FIELD_CHUNKS_SENT: stream["chunks"],
        FIELD_BYTES_SENT: stream["bytes"],
    }
    if error_code is not None:
        fields[FIELD_ERROR_CODE] = error_code
    if error_class is not None:
        fields[FIELD_ERROR_CLASS] = error_class
    log_event(logger, event, message=message, level=level, **fields)


class RequestContextMiddleware:
    """Pure ASGI middleware: request id propagation, request and stream events."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = request_context.resolve_request_id(
            _header_value(scope, request_context.REQUEST_ID_HEADER)
        )
        started = time.perf_counter()
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["request_started"] = started
        method = scope.get("method", "")

        status_code: int | None = None
        stream: dict[str, Any] | None = None

        async def send_with_context(message: dict) -> None:
            nonlocal status_code, stream
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers") or ())
                headers.append(
                    (
                        request_context.REQUEST_ID_HEADER.lower().encode("latin-1"),
                        request_id.encode("latin-1"),
                    )
                )
                message = {**message, "headers": headers}
                if _SSE_CONTENT_TYPE in _content_type(headers):
                    stream = {"chunks": 0, "bytes": 0, "completed": False}
                    _log_stream_event(
                        EVENT_SSE_STARTED,
                        scope,
                        method=method,
                        stream=stream,
                        level=logging.INFO,
                        message="SSE 流开始",
                    )
            elif message["type"] == "http.response.body" and stream is not None:
                body = message.get("body") or b""
                if body:
                    stream["chunks"] += 1
                    stream["bytes"] += len(body)
                if not message.get("more_body", False):
                    stream["completed"] = True
            await send(message)

        with request_context.bind_request_context(request_id=request_id, user_id=None):
            try:
                await self.app(scope, receive, send_with_context)
            except asyncio.CancelledError:
                if stream is not None:
                    _log_stream_event(
                        EVENT_SSE_INTERRUPTED,
                        scope,
                        method=method,
                        stream=stream,
                        level=logging.WARNING,
                        message="SSE 流被中断",
                        error_code=ERROR_CODE_CLIENT_DISCONNECT,
                    )
                raise
            except Exception as exc:
                if stream is not None:
                    if isinstance(exc, ClientDisconnect):
                        _log_stream_event(
                            EVENT_SSE_INTERRUPTED,
                            scope,
                            method=method,
                            stream=stream,
                            level=logging.WARNING,
                            message="SSE 流被中断",
                            error_code=ERROR_CODE_CLIENT_DISCONNECT,
                        )
                    else:
                        _log_stream_event(
                            EVENT_SSE_FAILED,
                            scope,
                            method=method,
                            stream=stream,
                            level=logging.WARNING,
                            message="SSE 流上游失败",
                            error_code=ERROR_CODE_STREAM_FAILED,
                            error_class=type(root_cause(exc)).__name__,
                        )
                raise
            else:
                stream_error = _stream_error(scope)
                if stream is not None:
                    if not stream["completed"]:
                        # Starlette cancels the stream without a final frame when the
                        # client disconnects mid-stream.
                        _log_stream_event(
                            EVENT_SSE_INTERRUPTED,
                            scope,
                            method=method,
                            stream=stream,
                            level=logging.WARNING,
                            message="SSE 流被中断",
                            error_code=ERROR_CODE_CLIENT_DISCONNECT,
                        )
                    elif stream_error is not None:
                        # The route converted an upstream failure into a protocol frame,
                        # so the stream itself ended cleanly; keep the failure category.
                        _log_stream_event(
                            EVENT_SSE_FAILED,
                            scope,
                            method=method,
                            stream=stream,
                            level=logging.WARNING,
                            message="SSE 流上游失败",
                            error_code=stream_error.get(FIELD_ERROR_CODE),
                            error_class=stream_error.get(FIELD_ERROR_CLASS),
                        )
                    else:
                        _log_stream_event(
                            EVENT_SSE_COMPLETED,
                            scope,
                            method=method,
                            stream=stream,
                            level=logging.INFO,
                            message="SSE 流正常结束",
                        )
                _log_request_completed(
                    scope,
                    method=method,
                    status_code=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                )
