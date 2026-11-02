"""Single-line structured logging with stable field names and central redaction.

One event is one line: either JSON (non-development) or a compact human readable
rendering (development). Both renderings expose the same field set, so local and
production log queries stay compatible. Secrets are removed in one place instead
of relying on every call site to remember them.
"""

import datetime
import json
import logging
import re
import traceback
from collections.abc import Mapping
from typing import Any

from app.core import request_context
from app.core.config import settings

# --- Fixed field names (single source of truth; no synonyms allowed) ---------
FIELD_TIMESTAMP = "timestamp"
FIELD_LEVEL = "level"
FIELD_EVENT = "event"
FIELD_MESSAGE = "message"
FIELD_REQUEST_ID = "request_id"
FIELD_USER_ID = "user_id"
FIELD_ROUTE = "route"
FIELD_METHOD = "method"
FIELD_STATUS_CODE = "status_code"
FIELD_DURATION_MS = "duration_ms"
FIELD_ERROR_CODE = "error_code"
FIELD_ERROR_CLASS = "error_class"
FIELD_TASK_ID = "task_id"
FIELD_DEPENDENCY = "dependency"
FIELD_ATTEMPT = "attempt"
FIELD_VERSION = "version"
FIELD_STACK = "stack"
FIELD_CHUNKS_SENT = "chunks_sent"
FIELD_BYTES_SENT = "bytes_sent"
FIELD_MODEL_PURPOSE = "model_purpose"
FIELD_LLM_MODE = "llm_mode"
FIELD_ERROR_CATEGORY = "error_category"
FIELD_PROMPT_CHARS = "prompt_chars"
FIELD_IMAGE_SIZE_BYTES = "image_size_bytes"
FIELD_PLAN_ID = "plan_id"
FIELD_ADJUSTMENT_ID = "adjustment_id"
FIELD_DIRECTION = "direction"
FIELD_COMPLETION_RATE = "completion_rate"
FIELD_RULE_CODE = "rule_code"
FIELD_EVALUATED_USERS = "evaluated_users"
FIELD_DELIVERED = "delivered"
FIELD_DUPLICATES = "duplicates"
FIELD_FAILED = "failed"
FIELD_SKIPPED = "skipped"

# --- Stable event names: domain.action.result -------------------------------
EVENT_HTTP_COMPLETED = "http.request.completed"
EVENT_HTTP_FAILED = "http.request.failed"
EVENT_HTTP_SLOW = "http.request.slow"
EVENT_SSE_STARTED = "stream.sse.started"
EVENT_SSE_COMPLETED = "stream.sse.completed"
EVENT_SSE_INTERRUPTED = "stream.sse.interrupted"
EVENT_SSE_FAILED = "stream.sse.failed"
EVENT_TASK_CREATED = "task.analysis.created"
EVENT_TASK_STARTED = "task.analysis.started"
EVENT_TASK_COMPLETED = "task.analysis.completed"
EVENT_TASK_FAILED = "task.analysis.failed"
EVENT_TASK_CLAIMED = "task.analysis.claimed"
EVENT_TASK_RECLAIMED = "task.analysis.reclaimed"
EVENT_TASK_EXPIRED = "task.analysis.expired"
EVENT_TASK_CLEANED = "task.analysis.cleaned"
EVENT_DEPENDENCY_FAILED = "dependency.probe.failed"
EVENT_DEPENDENCY_RECOVERED = "dependency.probe.recovered"
EVENT_LLM_COMPLETED = "llm.call.completed"
EVENT_LLM_FAILED = "llm.call.failed"
EVENT_LLM_DEGRADED = "llm.output.degraded"
EVENT_PLAN_ADJUSTMENT_APPLIED = "plan.adjustment.applied"
EVENT_PLAN_ADJUSTMENT_FAILED = "plan.adjustment.failed"
EVENT_REMINDER_TICK_COMPLETED = "reminder.tick.completed"
EVENT_REMINDER_TICK_FAILED = "reminder.tick.failed"
EVENT_REMINDER_DELIVERY_FAILED = "reminder.delivery.failed"

# Event used for log calls that predate the structured event vocabulary.
FALLBACK_EVENT = "log.record.emitted"

# --- Stable error codes ------------------------------------------------------
ERROR_CODE_HTTP_PREFIX = "http_"
ERROR_CODE_TASK_FAILED = "task_failed"
ERROR_CODE_STREAM_FAILED = "stream_failed"
ERROR_CODE_CLIENT_DISCONNECT = "client_disconnect"
ERROR_CODE_ADJUSTMENT_PERSIST_FAILED = "adjustment_persist_failed"

# --- Redaction ---------------------------------------------------------------
REDACTED = "[redacted]"
STRUCTURED_HANDLER_ATTR = "_lianleme_structured_handler"

# Field names that may never reach the log stream, normalized to [a-z0-9].
_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "apikey",
        "apikeys",
        "authorization",
        "password",
        "passwd",
        "token",
        "accesstoken",
        "refreshtoken",
        "secret",
        "secretkey",
        "aessecretkey",
        "prompt",
        "prompts",
        "systemprompt",
        "userprompt",
        "messages",
        "conversation",
        "chatmessage",
        "chatmessages",
        "imagebase64",
        "imagebytes",
        "imagecontent",
        "rawimage",
    }
)

# Value shapes that must be scrubbed even when they land in an allowed field.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+"),
    re.compile(r"[A-Za-z0-9+/]{120,}={0,2}"),
)


def _normalize_field_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _is_forbidden_field(name: Any) -> bool:
    return _normalize_field_name(name) in _FORBIDDEN_FIELD_NAMES


def redact_text(value: str) -> str:
    """Scrub secret-shaped substrings from a free-form string."""
    for pattern in _SECRET_VALUE_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def redact_value(value: Any) -> Any:
    """Recursively scrub a structured value."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value


def redact_mapping(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Drop forbidden fields and scrub the remaining values."""
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if _is_forbidden_field(key):
            continue
        cleaned[str(key)] = redact_value(value)
    return cleaned


def _format_timestamp(created: float) -> str:
    return datetime.datetime.fromtimestamp(
        created, tz=datetime.timezone.utc
    ).isoformat(timespec="milliseconds")


def root_cause(exc: BaseException) -> BaseException:
    """Return the leaf exception, unwrapping single-cause task-group wrappers."""
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    message: str = "",
    level: int = logging.INFO,
    exc_info: Any = None,
    **fields: Any,
) -> None:
    """Emit one structured event; correlation fields come from the context."""
    payload: dict[str, Any] = {
        FIELD_REQUEST_ID: request_context.get_request_id(),
        FIELD_USER_ID: request_context.get_user_id(),
    }
    task_id = request_context.get_task_id()
    if task_id is not None:
        payload[FIELD_TASK_ID] = task_id
    attempt = request_context.get_attempt()
    if attempt is not None:
        payload[FIELD_ATTEMPT] = attempt
    payload.update(fields)
    payload[FIELD_EVENT] = event
    payload[FIELD_MESSAGE] = message
    logger.log(
        level,
        message,
        extra={"fields": redact_mapping(payload)},
        exc_info=exc_info,
    )


class _BaseStructuredFormatter(logging.Formatter):
    """Build the canonical field mapping shared by every output format."""

    def build_payload(self, record: logging.LogRecord) -> dict[str, Any]:
        raw_fields = getattr(record, "fields", None)
        extra: dict[str, Any] = dict(raw_fields) if isinstance(raw_fields, Mapping) else {}

        event = extra.pop(FIELD_EVENT, FALLBACK_EVENT)
        message = extra.pop(FIELD_MESSAGE, record.getMessage())
        payload: dict[str, Any] = {
            FIELD_TIMESTAMP: _format_timestamp(record.created),
            FIELD_LEVEL: record.levelname.lower(),
            FIELD_EVENT: event,
            FIELD_MESSAGE: message,
        }

        if FIELD_REQUEST_ID not in extra:
            extra[FIELD_REQUEST_ID] = request_context.get_request_id()
        if FIELD_USER_ID not in extra:
            extra[FIELD_USER_ID] = request_context.get_user_id()
        if FIELD_STACK not in extra:
            if record.exc_info:
                extra[FIELD_STACK] = "".join(traceback.format_exception(*record.exc_info))
            elif record.stack_info:
                extra[FIELD_STACK] = record.stack_info

        payload.update(extra)
        return redact_mapping(payload)


class StructuredJsonFormatter(_BaseStructuredFormatter):
    """Render one event as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            self.build_payload(record), ensure_ascii=False, default=str, separators=(",", ":")
        )


class HumanReadableFormatter(_BaseStructuredFormatter):
    """Render the same fields as one compact key=value line for local reading."""

    def format(self, record: logging.LogRecord) -> str:
        payload = self.build_payload(record)
        timestamp = payload.pop(FIELD_TIMESTAMP)
        level = str(payload.pop(FIELD_LEVEL)).upper()
        message = str(payload.pop(FIELD_MESSAGE)).replace("\n", "\\n")
        extras = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
            for key, value in payload.items()
        )
        prefix = f"{timestamp} {level} {message}"
        return f"{prefix} | {extras}" if extras else prefix


def create_formatter(
    app_env: str | None = None, log_format: str | None = None
) -> logging.Formatter:
    """Pick the output format: JSON outside development, human readable in dev."""
    resolved_env = (settings.APP_ENV if app_env is None else app_env or "")
    resolved_env = resolved_env.strip().lower()
    resolved_format = (settings.LOG_FORMAT if log_format is None else log_format or "")
    resolved_format = resolved_format.strip().lower() or "auto"
    if resolved_format == "json":
        return StructuredJsonFormatter()
    if resolved_format == "text":
        return HumanReadableFormatter()
    if resolved_env == "development":
        return HumanReadableFormatter()
    return StructuredJsonFormatter()


def _coerce_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level
    resolved = logging.getLevelName(str(level or settings.LOG_LEVEL).strip().upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def configure_logging(
    *,
    app_env: str | None = None,
    level: str | int | None = None,
    log_format: str | None = None,
) -> logging.Handler:
    """Install exactly one structured handler on the root logger."""
    numeric_level = _coerce_level(level)
    root = logging.getLogger()
    for handler in [
        existing
        for existing in root.handlers
        if getattr(existing, STRUCTURED_HANDLER_ATTR, False)
    ]:
        root.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler()
    setattr(handler, STRUCTURED_HANDLER_ATTR, True)
    handler.setLevel(numeric_level)
    handler.setFormatter(create_formatter(app_env=app_env, log_format=log_format))
    root.addHandler(handler)
    root.setLevel(numeric_level)
    return handler
