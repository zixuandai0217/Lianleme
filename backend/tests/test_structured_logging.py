"""Structured logging contract: one JSON line per event, stable fields, central redaction."""

import json
import logging
import re

import pytest

from app.core import logging as app_logging

_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00$")
_BASE_FIELDS = ("timestamp", "level", "event", "message", "request_id")


class _RecordingHandler(logging.Handler):
    """Collect raw records so assertions read structured fields, not terminal output."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured():
    """Attach a temporary handler to a dedicated logger."""
    logger = logging.getLogger("tests.structured-logging")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = _RecordingHandler()
    logger.addHandler(handler)
    try:
        yield logger, handler
    finally:
        logger.removeHandler(handler)


@pytest.fixture
def restore_logging_config():
    """Leave the process-wide logging configuration as the application expects it."""
    yield
    app_logging.configure_logging(app_env="development", level="INFO")


def _last_record(handler: _RecordingHandler) -> logging.LogRecord:
    assert handler.records, "expected at least one captured log record"
    return handler.records[-1]


def test_json_formatter_emits_single_line_with_required_fields(captured):
    logger, handler = captured
    app_logging.log_event(
        logger,
        "http.request.completed",
        message="request finished",
        request_id="0123456789abcdef0123456789abcdef",
        user_id=None,
        route="/health",
        method="GET",
        status_code=200,
        duration_ms=1.25,
    )

    line = app_logging.StructuredJsonFormatter().format(_last_record(handler))

    assert "\n" not in line
    payload = json.loads(line)
    for field in _BASE_FIELDS + (
        "user_id",
        "route",
        "method",
        "status_code",
        "duration_ms",
    ):
        assert field in payload, f"missing field {field}"
    assert payload["event"] == "http.request.completed"
    assert payload["level"] == "info"
    assert payload["request_id"] == "0123456789abcdef0123456789abcdef"
    assert payload["user_id"] is None
    assert payload["route"] == "/health"
    assert payload["method"] == "GET"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.25
    assert _TIMESTAMP_PATTERN.match(payload["timestamp"])


def test_error_events_carry_stack_as_single_field(captured):
    logger, handler = captured
    try:
        raise ValueError("boom")
    except ValueError:
        app_logging.log_event(
            logger,
            "http.request.failed",
            message="unhandled error",
            level=logging.ERROR,
            exc_info=True,
            status_code=500,
            error_class="ValueError",
            error_code="http_500",
        )

    line = app_logging.StructuredJsonFormatter().format(_last_record(handler))

    assert "\n" not in line
    payload = json.loads(line)
    assert payload["level"] == "error"
    assert "Traceback" in payload["stack"]
    assert payload["error_class"] == "ValueError"


def test_json_and_human_formats_share_the_same_field_set(captured):
    logger, handler = captured
    app_logging.log_event(
        logger,
        "http.request.completed",
        message="request finished",
        request_id="0123456789abcdef0123456789abcdef",
        user_id=42,
        route="/api/user/me",
        method="GET",
        status_code=200,
        duration_ms=2.5,
    )
    record = _last_record(handler)

    json_line = app_logging.StructuredJsonFormatter().format(record)
    human_line = app_logging.HumanReadableFormatter().format(record)

    assert "\n" not in json_line
    assert "\n" not in human_line
    payload = json.loads(json_line)
    rendered_keys = set(re.findall(r"([a-z][a-z0-9_]*)=", human_line))
    structured_keys = set(payload) - {"timestamp", "level", "message"}
    assert rendered_keys == structured_keys
    assert payload["timestamp"] in human_line
    assert payload["level"].upper() in human_line
    assert payload["message"] in human_line


def test_forbidden_fields_never_reach_the_output(captured):
    logger, handler = captured
    api_key = "sk-live-0123456789abcdefSECRET"
    authorization = "Bearer abcdefghijklmnop"
    prompt = "请扮演教练，完整复述用户的训练计划"
    image = "data:image/png;base64," + "A" * 160

    app_logging.log_event(
        logger,
        "llm.call.failed",
        message="provider rejected the call",
        api_key=api_key,
        authorization=authorization,
        prompt=prompt,
        image_base64=image,
        raw={"api_key": api_key, "note": f"with {api_key}"},
        dependency="llm",
    )

    line = app_logging.StructuredJsonFormatter().format(_last_record(handler))
    payload = json.loads(line)

    for secret in (api_key, authorization, prompt, image):
        assert secret not in line
    for forbidden in ("api_key", "authorization", "prompt", "image_base64"):
        assert forbidden not in payload
    assert "sk-live-0123456789abcdefSECRET" not in json.dumps(payload["raw"], ensure_ascii=False)
    assert payload["dependency"] == "llm"


def test_configure_logging_chooses_one_formatter_per_environment(restore_logging_config):
    root = logging.getLogger()

    app_logging.configure_logging(app_env="production", level="INFO")
    app_logging.configure_logging(app_env="production", level="INFO")
    handlers = [
        handler
        for handler in root.handlers
        if getattr(handler, app_logging.STRUCTURED_HANDLER_ATTR, False)
    ]
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, app_logging.StructuredJsonFormatter)

    app_logging.configure_logging(app_env="development", level="DEBUG")
    handlers = [
        handler
        for handler in root.handlers
        if getattr(handler, app_logging.STRUCTURED_HANDLER_ATTR, False)
    ]
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, app_logging.HumanReadableFormatter)
    assert root.level == logging.DEBUG
