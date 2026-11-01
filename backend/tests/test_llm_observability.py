"""LLM 调用观测契约：成功/失败/降级事件、错误分类、BYOK/系统回退标记与脱敏。

断言只落在「一次真实路由调用产生了哪些事件、事件里有什么字段」这一层：
调用点内部实现可以换（同步/流式/换供应商），这几个事实不能丢。
"""

import json
import logging
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import logging as app_logging
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import StructuredJsonFormatter
from app.core.request_context import REQUEST_ID_HEADER
from app.core.security import require_current_user_api_key
from app.main import app
from app.services.ai import coach_graph as coach_graph_module
from app.services.ai import llm_observability as observed
from app.services.ai.coach_graph import COACH_FALLBACK_REPLY, CoachGraph
from app.services.ai.llm_factory import LLMClientFactory
from app.services.ai.tts_service import QwenTTSAPIError
from app.services.ai.vision_graph import VisionGraph

USER_ID = 41
CHAT_URL = "/api/coach/chat"

_DOCUMENTED_FIELDS = {
    getattr(app_logging, name)
    for name in dir(app_logging)
    if name.startswith("FIELD_")
}



class AuthenticationError(Exception):
    """Provider rejected the credentials."""


class RateLimitError(Exception):
    """Provider throttled the caller."""


class APITimeoutError(Exception):
    """Provider did not answer in time."""


class APIConnectionError(Exception):
    """Provider was unreachable."""


class OutputParserException(Exception):
    """Provider answered with unparseable output."""


@pytest.fixture(autouse=True)
def capture_logs(caplog):
    caplog.set_level(logging.INFO)
    return caplog


@pytest_asyncio.fixture
async def client():
    async def override_get_db():
        yield object()

    async def override_current_user():
        return SimpleNamespace(id=USER_ID)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_current_user_api_key] = override_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://llm.test"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


class FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc_info):
        return False


def install_fake_llm(
    monkeypatch,
    *,
    reply: str = '{"reply": "开练吧 homie", "coach_state": "guide", "suggested_actions": []}',
    error: BaseException | None = None,
    provider: str = "qwen",
    mode: str = "byok",
):
    """Replace the provider call but keep the graph, route and logging real."""

    async def fake_load_history(self, db):
        return []

    async def fake_save_message(self, db, role, content):
        return None

    class FakeLLM:
        def __init__(self):
            self.llm_provider = provider
            self.llm_mode = mode

        async def ainvoke(self, messages, **kwargs):
            if error is not None:
                raise error
            return SimpleNamespace(content=reply)

        async def astream(self, messages, **kwargs):
            if error is not None:
                raise error
            yield SimpleNamespace(content=reply)

    async def fake_get_client(self, user_id, model_type, streaming=False):
        return FakeLLM()

    monkeypatch.setattr(CoachGraph, "_load_history", fake_load_history)
    monkeypatch.setattr(CoachGraph, "_save_message", fake_save_message)
    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)
    monkeypatch.setattr(coach_graph_module, "AsyncSessionLocal", lambda: FakeSessionContext())


def _payloads(caplog) -> list[dict]:
    formatter = StructuredJsonFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if getattr(record, "fields", None) is not None
    ]


def _events(caplog, event: str) -> list[dict]:
    return [payload for payload in _payloads(caplog) if payload.get("event") == event]


async def post_chat(client: AsyncClient, message: str = "今天练什么"):
    return await client.post(CHAT_URL, json={"user_id": USER_ID, "message": message})


@pytest.mark.asyncio
async def test_successful_call_records_duration_and_byok_mode(monkeypatch, client, caplog):
    install_fake_llm(monkeypatch, provider="qwen", mode="byok")

    response = await post_chat(client)

    assert response.status_code == 200
    events = _events(caplog, observed.EVENT_LLM_COMPLETED)
    assert events, "a successful provider call must produce one completion event"
    event = events[-1]
    assert event["dependency"] == "qwen"
    assert event["model_purpose"] == observed.PURPOSE_CHAT
    assert event["llm_mode"] == observed.MODE_BYOK
    assert event["duration_ms"] >= 0
    assert event["prompt_chars"] > 0
    assert event["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert event["level"] == "info"


@pytest.mark.asyncio
async def test_system_fallback_mode_is_distinguishable_from_byok(monkeypatch, client, caplog):
    install_fake_llm(monkeypatch, provider="qwen", mode="system")

    response = await post_chat(client)

    assert response.status_code == 200
    event = _events(caplog, observed.EVENT_LLM_COMPLETED)[-1]
    assert event["llm_mode"] == observed.MODE_SYSTEM
    assert event["llm_mode"] != observed.MODE_BYOK


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_category"),
    [
        (AuthenticationError("invalid api key"), observed.ERROR_CATEGORY_AUTH),
        (RateLimitError("429 too many requests"), observed.ERROR_CATEGORY_RATE_LIMIT),
        (APITimeoutError("read timeout"), observed.ERROR_CATEGORY_TIMEOUT),
        (APIConnectionError("connection reset by peer"), observed.ERROR_CATEGORY_NETWORK),
        (OutputParserException("could not parse output"), observed.ERROR_CATEGORY_OUTPUT_PARSE),
        (RuntimeError("unexpected provider failure"), observed.ERROR_CATEGORY_UNKNOWN),
    ],
)
async def test_failed_call_events_separate_the_error_categories(
    monkeypatch, client, caplog, error, expected_category
):
    install_fake_llm(monkeypatch, error=error)

    response = await post_chat(client)

    assert response.status_code == 500
    events = _events(caplog, observed.EVENT_LLM_FAILED)
    assert events, "a failed provider call must produce a failure event"
    event = events[-1]
    assert event["error_category"] == expected_category
    assert event["dependency"] == "qwen"
    assert event["model_purpose"] == observed.PURPOSE_CHAT
    assert event["llm_mode"] == observed.MODE_BYOK
    assert event["error_class"] == type(error).__name__
    assert event["duration_ms"] >= 0
    assert event["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert event["level"] == "warning"
    assert "stack" not in event


@pytest.mark.asyncio
async def test_unparseable_output_is_a_separate_degradation_event(monkeypatch, client, caplog):
    install_fake_llm(monkeypatch, reply='{"unexpected": "envelope"}')

    response = await post_chat(client)

    assert response.status_code == 200
    assert response.json()["reply"] == COACH_FALLBACK_REPLY
    degraded = _events(caplog, observed.EVENT_LLM_DEGRADED)
    assert degraded, "a fallback reply must be recorded as a separate degradation event"
    event = degraded[-1]
    assert event["event"] != observed.EVENT_LLM_COMPLETED
    assert event["model_purpose"] == observed.PURPOSE_CHAT
    assert event["error_code"]
    assert event["level"] == "warning"


@pytest.mark.asyncio
async def test_logs_never_contain_keys_prompts_or_conversation_text(monkeypatch, client, caplog):
    masked_key = "sk-...****mnop"
    prompt_marker = "PROMPT-MARKER-8f3a"
    conversation_marker = f"{prompt_marker} 我的深蹲膝盖有点疼 {masked_key}"
    install_fake_llm(monkeypatch, error=AuthenticationError(conversation_marker))

    response = await post_chat(client, message=conversation_marker)

    assert response.status_code == 500
    rendered = "\n".join(
        StructuredJsonFormatter().format(record)
        for record in caplog.records
        if getattr(record, "fields", None) is not None
    )
    assert conversation_marker not in rendered
    assert masked_key not in rendered
    assert prompt_marker not in rendered
    event = _events(caplog, observed.EVENT_LLM_FAILED)[-1]
    assert event["prompt_chars"] >= len(conversation_marker)


@pytest.mark.asyncio
async def test_stream_failure_is_classified_without_leaking_provider_content(
    monkeypatch, client, caplog
):
    secret = "provider-echo-PROMPT-9c7f sk-...****secret"
    install_fake_llm(monkeypatch, error=RateLimitError(secret))

    response = await client.post(
        "/api/coach/chat/stream", json={"user_id": USER_ID, "message": "开练"}
    )

    assert response.status_code == 200
    assert '"rate_limited"' in response.text
    event = _events(caplog, observed.EVENT_LLM_FAILED)[-1]
    assert event["error_category"] == "rate_limit"
    assert event["request_id"] == response.headers[REQUEST_ID_HEADER]
    rendered = "\n".join(StructuredJsonFormatter().format(record) for record in caplog.records)
    assert secret not in rendered


@pytest.mark.asyncio
async def test_stream_structured_output_emits_separate_degradation(monkeypatch, client, caplog):
    """A fenced block without a usable reply falls back and is recorded."""
    fenced = "```json" + chr(10) + '{"unexpected": "x"}' + chr(10) + "```"
    install_fake_llm(monkeypatch, reply=fenced)

    response = await client.post(
        "/api/coach/chat/stream", json={"user_id": USER_ID, "message": "开练"}
    )

    assert response.status_code == 200
    assert _events(caplog, observed.EVENT_LLM_COMPLETED)
    assert _events(caplog, observed.EVENT_LLM_DEGRADED)

@pytest.mark.asyncio
async def test_llm_event_field_names_follow_the_logging_contract(monkeypatch, client, caplog):
    install_fake_llm(monkeypatch, error=RateLimitError("429"))

    await post_chat(client)

    llm_events = [
        payload for payload in _payloads(caplog) if str(payload.get("event", "")).startswith("llm.")
    ]
    assert llm_events
    for payload in llm_events:
        assert set(payload) <= _DOCUMENTED_FIELDS, f"undocumented field in {payload}"
        for alias in ("req_id", "requestId", "uid", "provider", "purpose", "llmProvider"):
            assert alias not in payload, f"field alias {alias} must not be used"




@pytest.mark.asyncio
async def test_vision_call_records_image_size_without_logging_content(monkeypatch, caplog):
    """The multimodal path must carry the same fields, and never the image itself."""
    image_base64 = "QUJD" * 120
    seen_messages: list = []

    class FakeVisionLLM:
        llm_provider = "qwen"
        llm_mode = "byok"

        async def ainvoke(self, messages, **kwargs):
            seen_messages.extend(messages)
            return SimpleNamespace(content="not a parsable body")

    async def fake_get_client(self, user_id, model_type, streaming=False):
        return FakeVisionLLM()

    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)

    result = await VisionGraph(user_id=USER_ID, db=None).run(image_base64=image_base64)

    assert result is not None
    events = _events(caplog, observed.EVENT_LLM_COMPLETED)
    assert events, "the multimodal call must produce a completion event"
    event = events[-1]
    assert event["model_purpose"] == observed.PURPOSE_VISION
    assert event["dependency"] == "qwen"
    assert event["llm_mode"] == observed.MODE_BYOK
    assert event["image_size_bytes"] >= 300
    assert event["prompt_chars"] > 0

    degraded = _events(caplog, observed.EVENT_LLM_DEGRADED)
    assert degraded and degraded[-1]["model_purpose"] == observed.PURPOSE_VISION

    rendered = "\n".join(
        StructuredJsonFormatter().format(record) for record in caplog.records
    )
    assert image_base64 not in rendered, "image content must never reach the log"


@pytest.mark.asyncio
async def test_voice_call_records_purpose_and_failure_category(monkeypatch, caplog):
    """Speech synthesis shares the same outcome vocabulary as chat/vision."""
    from app.services.ai import tts_runtime

    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_VOICE", "voice-abc")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "voice-key")
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "clear_tts_cache", lambda: None)
    tts_runtime.clear_tts_cache()

    class FailingSpeechClient:
        async def synthesize(self, *, text, voice_id):
            raise QwenTTSAPIError("provider failed") from TimeoutError("slow")

    monkeypatch.setattr(tts_runtime, "_build_client", lambda *args, **kwargs: FailingSpeechClient())

    with pytest.raises(observed.LLMCallError):
        await tts_runtime.synthesize_speech("hello coach", llm_mode="byok")

    event = _events(caplog, observed.EVENT_LLM_FAILED)[-1]
    assert event["model_purpose"] == observed.PURPOSE_VOICE
    assert event["dependency"] == "qwen"
    assert event["llm_mode"] == observed.MODE_BYOK
    assert event["error_category"] == observed.ERROR_CATEGORY_TIMEOUT
    assert event["prompt_chars"] == len("hello coach")


@pytest.mark.asyncio
async def test_factory_provenance_comes_from_the_key_actually_used(monkeypatch):
    """BYOK vs system fallback must be decided at resolution, not guessed later."""
    from app.services.user import api_key_service

    async def byok_key(self, user_id):
        return ("qwen", "sk-user-owned-key-123456")

    monkeypatch.setattr(api_key_service.ApiKeyService, "get_decrypted_key", byok_key)
    byok_client = await LLMClientFactory(db=object()).get_client(user_id=USER_ID)
    assert observed.client_provenance(byok_client) == observed.ClientProvenance("qwen", "byok")

    async def no_user_key(self, user_id):
        return None

    monkeypatch.setattr(api_key_service.ApiKeyService, "get_decrypted_key", no_user_key)
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "QWEN_API_KEY", "sk-system-owned-key-654321")
    system_client = await LLMClientFactory(db=object()).get_client(user_id=USER_ID)
    assert observed.client_provenance(system_client) == observed.ClientProvenance(
        "qwen", "system"
    )
