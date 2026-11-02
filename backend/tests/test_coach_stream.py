"""Route-level contract tests for the AI coach SSE event stream.

The stream is a typed event stream: one JSON object per single-line ``data:``
frame. Tests drive the route through an ASGI client with auth/database
dependencies overridden and a fake CoachGraph, so no provider call is made.
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api import coach as coach_api
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.logging import EVENT_SSE_INTERRUPTED
from app.core.security import get_current_user, require_current_user_api_key
from app.main import app
from app.models.chat_message import ChatMessageRecord
from app.models.user import User
from app.schemas.chat import (
    CoachAction,
    CoachActionsEvent,
    CoachDoneEvent,
    CoachErrorEvent,
    CoachMessageChunkEvent,
    CoachStateEvent,
    CoachTurnStartedEvent,
    sse_frame,
)
from app.services.ai import coach_graph as coach_graph_module
from app.services.ai.coach_graph import COACH_FALLBACK_REPLY, CoachGraph
from app.services.ai.llm_factory import LLMClientFactory
from app.services.user.api_key_service import ApiKeyService

USER_ID = 7
STREAM_URL = "/api/coach/chat/stream"
CHAT_URL = "/api/coach/chat"
ERROR_CODES = {"provider_unavailable", "rate_limited", "upstream_timeout", "internal"}


def decode_frames(body: str) -> list[dict]:
    """Decode the SSE body with one JSON object per single-line data frame."""
    assert body.endswith("\n\n"), f"stream must end with a complete frame: {body!r}"
    frames: list[dict] = []
    for block in body.split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        assert len(lines) == 1, f"a frame must stay on one line: {block!r}"
        line = lines[0]
        assert line.startswith("data: "), f"unexpected frame line: {line!r}"
        payload = line[len("data: "):]
        assert payload != "[DONE]", "the legacy DONE marker must not be used anymore"
        frames.append(json.loads(payload))
    return frames


def visible_text(frames: list[dict]) -> str:
    """Rebuild the user-visible reply exclusively from delta frames."""
    return "".join(frame["text"] for frame in frames if frame["type"] == "message_chunk")


def assert_stream_contract(frames: list[dict]) -> None:
    """Assert the opening/closing frame contract shared by every turn."""
    assert frames, "the stream must contain at least one frame"
    first, last = frames[0], frames[-1]
    assert first["type"] == "turn_started"
    assert first["protocol"] == 1
    assert isinstance(first["turn_id"], str) and first["turn_id"]
    assert isinstance(first["message_id"], str) and first["message_id"]
    assert last["type"] == "done"
    types = [frame["type"] for frame in frames]
    assert types.count("turn_started") == 1
    assert types.count("done") == 1
    for frame in frames:
        assert isinstance(frame["type"], str)
        if frame["type"] == "message_chunk":
            assert frame["text"], "delta frames must never be empty"


@asynccontextmanager
async def coach_client():
    """App client wired to fake auth and a disposable database session."""

    async def override_get_db():
        yield object()

    async def override_current_user():
        return SimpleNamespace(id=USER_ID)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_current_user_api_key] = override_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def post_stream(client: AsyncClient, message: str = "hello"):
    """Post one coach turn and return the raw response."""
    return await client.post(
        STREAM_URL,
        json={"user_id": USER_ID, "message": message},
    )


def scripted_coach_graph(tokens: list[str]):
    """Build a fake graph that replays fixed model tokens."""

    class ScriptedCoachGraph:
        def __init__(self, user_id: int, db: object):
            self.user_id = user_id
            self.db = db

        async def stream_chat(self, message: str, context: dict):
            for token in tokens:
                yield token

        async def save_turn(self, message: str, reply: str, *, actions=None, coach_state=None):
            self.saved = (message, reply)

    return ScriptedCoachGraph


class FailingCoachGraph:
    """Simulate an upstream provider failure after the SSE response started."""

    def __init__(self, user_id: int, db: object):
        self.user_id = user_id
        self.db = db

    async def stream_chat(self, message: str, context: dict):
        """Raise the same class of failure produced by an invalid provider key."""
        if False:
            yield ""
        raise RuntimeError("invalid provider key")

    async def save_turn(self, message: str, reply: str, *, actions=None, coach_state=None):
        raise AssertionError("a failed turn must not be persisted")


class FakeSessionContext:
    """Stand-in for the session context manager the graph opens itself."""

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc_info):
        return False


def install_fake_llm(monkeypatch, tokens: list[str], collector: list[tuple[str, str]]):
    """Replace the graph's provider and persistence so only the protocol is real."""

    async def fake_load_history(self, db):
        return []

    async def fake_save_message(self, db, role, content):
        collector.append((role, content))

    class FakeStreamingLLM:
        async def astream(self, messages):
            for token in tokens:
                yield SimpleNamespace(content=token)

    class FakeCompletingLLM:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="".join(tokens))

    async def fake_get_client(self, user_id, model_type, streaming=False):
        return FakeStreamingLLM() if streaming else FakeCompletingLLM()

    monkeypatch.setattr(CoachGraph, "_load_history", fake_load_history)
    monkeypatch.setattr(CoachGraph, "_save_message", fake_save_message)
    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)
    monkeypatch.setattr(
        coach_graph_module,
        "AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )


@pytest.mark.asyncio
async def test_stream_frames_follow_the_protocol_contract(monkeypatch):
    """A normal turn opens with turn_started, carries deltas, and closes with one done."""
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        scripted_coach_graph(["开练吧 homie，", "先练胸。"]),
    )

    async with coach_client() as client:
        response = await post_stream(client)

    assert response.status_code == 200
    frames = decode_frames(response.text)
    assert_stream_contract(frames)
    assert [frame["type"] for frame in frames] == [
        "turn_started",
        "message_chunk",
        "message_chunk",
        "state",
        "actions",
        "done",
    ]
    assert visible_text(frames) == "开练吧 homie，先练胸。"
    assert frames[-1]["finish_reason"] == "complete"


@pytest.mark.asyncio
async def test_json_shell_output_is_cleaned_before_reaching_the_bubble(monkeypatch):
    """A JSON wrapper never reaches the user; only its reply field becomes the body."""
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        scripted_coach_graph(
            [
                '{"reply": "bro 你这一组',
                '稳了", "suggested_actions": ["完成一组", "换个动作"]}',
            ]
        ),
    )

    async with coach_client() as client:
        response = await post_stream(client)

    frames = decode_frames(response.text)
    assert_stream_contract(frames)
    assert visible_text(frames) == "bro 你这一组稳了"
    assert '{"reply"' not in response.text
    assert "suggested_actions" not in response.text
    assert frames[-1]["finish_reason"] == "complete"


@pytest.mark.asyncio
async def test_code_blocks_and_newlines_never_break_frame_encoding(monkeypatch):
    """Multiline model output is cleaned and every frame stays valid single-line JSON."""
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        scripted_coach_graph(
            [
                "先把肩打开，homie。\n",
                "```python\nprint('warm up')\n```\n",
                "接着上杠铃。",
            ]
        ),
    )

    async with coach_client() as client:
        response = await post_stream(client)

    # decode_frames already asserts one-line JSON framing per event.
    frames = decode_frames(response.text)
    assert_stream_contract(frames)
    body = visible_text(frames)
    assert "```" not in body
    assert "print" not in body
    assert body.startswith("先把肩打开，homie。")
    assert body.endswith("接着上杠铃。")
    assert frames[-1]["finish_reason"] == "complete"


@pytest.mark.asyncio
async def test_same_model_text_cleans_identically_however_it_is_chunked(monkeypatch):
    """Cleaning is streaming and order preserving, so chunk boundaries do not matter."""
    tokens = [
        '```json\n{"reply": "先来 20 个深蹲，homie。\\n别偷懒", "actions": ["完成一组"]}\n```',
    ]
    whole = "".join(tokens)
    half = len(whole) // 2
    bodies: list[str] = []

    for chunking in (tokens, [whole], [whole[:half], whole[half:]], list(whole)):
        monkeypatch.setattr(coach_api, "CoachGraph", scripted_coach_graph(chunking))
        async with coach_client() as client:
            response = await post_stream(client)
        frames = decode_frames(response.text)
        assert_stream_contract(frames)
        bodies.append(visible_text(frames))

    assert len(set(bodies)) == 1
    assert bodies[0] == "先来 20 个深蹲，homie。\n别偷懒"


@pytest.mark.asyncio
async def test_unreadable_output_falls_back_to_one_readable_line(monkeypatch):
    """When cleaning leaves nothing readable a fixed fallback line keeps the turn usable."""
    unreadable = [
        '{"suggested_actions": ["完成一组"]}',
        '\n```json\n{"actions": []}\n```\n',
    ]
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        scripted_coach_graph(unreadable),
    )

    async with coach_client() as client:
        response = await post_stream(client)

    frames = decode_frames(response.text)
    assert_stream_contract(frames)
    assert visible_text(frames).strip() == COACH_FALLBACK_REPLY
    assert frames[-1]["finish_reason"] == "complete"


@pytest.mark.asyncio
async def test_upstream_failure_emits_error_frame_and_finishing_done(monkeypatch):
    """A mid-stream failure becomes an error frame, then done(error) — never a delta."""
    monkeypatch.setattr(coach_api, "CoachGraph", FailingCoachGraph)

    async with coach_client() as client:
        response = await post_stream(client)

    frames = decode_frames(response.text)
    assert_stream_contract(frames)
    assert [frame["type"] for frame in frames] == [
        "turn_started",
        "error",
        "state",
        "actions",
        "done",
    ]
    error = frames[1]
    assert error["code"] in ERROR_CODES
    assert isinstance(error["message"], str) and error["message"].strip()
    assert frames[-1]["finish_reason"] == "error"
    assert visible_text(frames) == ""


@pytest.mark.asyncio
async def test_cleaned_reply_is_what_gets_persisted(monkeypatch):
    """Persistence stores the cleaned body, so replay cannot leak raw structure."""
    saved: list[tuple[str, str]] = []
    install_fake_llm(
        monkeypatch,
        [
            '```json\n{"reply": "bro，今天先练腿。",',
            ' "suggested_actions": []}\n```',
        ],
        saved,
    )

    async with coach_client() as client:
        response = await post_stream(client, "今天练什么")

    frames = decode_frames(response.text)
    assert_stream_contract(frames)
    assert visible_text(frames) == "bro，今天先练腿。"
    assert saved == [("user", "今天练什么"), ("assistant", "bro，今天先练腿。")]


@pytest.mark.asyncio
async def test_non_stream_reply_is_cleaned_before_it_is_returned_and_saved(monkeypatch):
    """The JSON mode entry point shares the same cleaning, so both entries agree."""
    saved: list[tuple[str, str]] = []
    install_fake_llm(
        monkeypatch,
        ['```json\n{"reply": "先做热身，homie。", "coach_state": "count"}\n```'],
        saved,
    )

    async with coach_client() as client:
        response = await client.post(
            CHAT_URL,
            json={"user_id": USER_ID, "message": "开始吧"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "先做热身，homie。"
    # 状态由服务端确定性推导，模型自述的 count 不再决定呈现。
    assert payload["coach_state"] == "guide"
    assert payload["quick_actions"]
    assert payload["suggested_actions"] == [
        action["prompt"] for action in payload["quick_actions"]
    ]
    assert saved[-1] == ("assistant", "先做热身，homie。")


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            CoachTurnStartedEvent(turn_id="turn-1", message_id="message-1"),
            {
                "type": "turn_started",
                "protocol": 1,
                "turn_id": "turn-1",
                "message_id": "message-1",
            },
        ),
        (CoachMessageChunkEvent(text="hi"), {"type": "message_chunk", "text": "hi"}),
        (CoachStateEvent(coach_state="rest"), {"type": "state", "coach_state": "rest"}),
        (
            CoachActionsEvent(actions=[CoachAction(label="加一组", prompt="再加一组卧推")]),
            {
                "type": "actions",
                "actions": [{"label": "加一组", "prompt": "再加一组卧推"}],
            },
        ),
        (
            CoachErrorEvent(code="rate_limited", message="慢点再来"),
            {"type": "error", "code": "rate_limited", "message": "慢点再来"},
        ),
        (
            CoachDoneEvent(finish_reason="truncated"),
            {"type": "done", "finish_reason": "truncated"},
        ),
    ],
)
def test_single_frame_payload_matches_the_protocol_shape(event, expected):
    """Every frame type serializes to exactly one JSON line with spec §1 field names."""
    frame = sse_frame(event)

    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert "\n" not in frame[:-2]
    assert json.loads(frame[len("data: "):-2]) == expected


# ── 错误 / 中断 / 回放清洗（ticket 19）──


class PartiallyFailingCoachGraph:
    """Emit readable text, then fail the way a provider outage does."""

    def __init__(self, user_id: int, db: object):
        self.user_id = user_id
        self.db = db

    async def stream_chat(self, message: str, context: dict):
        yield "先来一组卧推"
        raise RuntimeError("invalid provider key")

    async def save_turn(self, message: str, reply: str, *, actions=None, coach_state=None):
        raise AssertionError("a failed turn must not be persisted")


def abortable_coach_graph(tokens: list[str], saved: list[tuple[str, str]]):
    """Build a graph that records persistence so an abort can prove it never ran."""

    class AbortableCoachGraph:
        def __init__(self, user_id: int, db: object):
            self.user_id = user_id
            self.db = db

        async def stream_chat(self, message: str, context: dict):
            for token in tokens:
                yield token

        async def save_turn(self, message: str, reply: str, *, actions=None, coach_state=None):
            saved.append((message, reply))

    return AbortableCoachGraph


def assert_plain_json_failure(response, status_code: int) -> dict:
    """A pre-stream failure must be plain JSON and never open an event stream."""
    assert response.status_code == status_code
    content_type = response.headers.get("content-type", "")
    assert "text/event-stream" not in content_type
    assert "data:" not in response.text
    assert "turn_started" not in response.text
    assert "message_chunk" not in response.text
    return response.json()


@asynccontextmanager
async def bare_client():
    """Client whose auth dependency runs for real, so 401 is produced by the app."""

    async def override_get_db():
        yield object()

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@asynccontextmanager
async def keyless_client():
    """Authenticated client that exercises the real key guard with no usable key."""

    async def override_get_db():
        yield object()

    async def override_current_user():
        return SimpleNamespace(id=USER_ID)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_unauthenticated_stream_request_is_plain_json_without_frames():
    """401 happens before the stream opens: JSON body, zero event frames."""
    async with bare_client() as client:
        response = await post_stream(client)

    payload = assert_plain_json_failure(response, 401)
    assert payload["detail"]


@pytest.mark.asyncio
async def test_identity_mismatch_is_plain_json_without_frames():
    """403 is a pre-stream JSON error, never an SSE frame."""
    async with coach_client() as client:
        response = await client.post(
            STREAM_URL,
            json={"user_id": USER_ID + 1, "message": "hi"},
        )

    payload = assert_plain_json_failure(response, 403)
    assert payload["detail"]


@pytest.mark.asyncio
async def test_keyless_user_gets_428_json_without_frames(monkeypatch):
    """The key guard fails closed at HTTP 428 with a plain JSON body and zero frames."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", False)

    async def no_user_key(self, user_id: int):
        return None

    monkeypatch.setattr(ApiKeyService, "get_decrypted_key", no_user_key)

    async with keyless_client() as client:
        response = await post_stream(client)

    payload = assert_plain_json_failure(response, 428)
    assert payload["detail"]["code"] == "api_key_required"
    assert payload["detail"]["message"]


@pytest.mark.asyncio
async def test_failure_after_partial_body_keeps_text_and_never_sends_error_as_delta(monkeypatch):
    """Partial body survives; the error is an event, never a delta frame."""
    monkeypatch.setattr(coach_api, "CoachGraph", PartiallyFailingCoachGraph)

    async with coach_client() as client:
        response = await post_stream(client)

    frames = decode_frames(response.text)
    assert_stream_contract(frames)
    assert [frame["type"] for frame in frames] == [
        "turn_started",
        "message_chunk",
        "error",
        "state",
        "actions",
        "done",
    ]
    error = frames[2]
    assert error["code"] in ERROR_CODES
    assert error["message"].strip()
    assert visible_text(frames) == "先来一组卧推"
    for frame in frames:
        if frame["type"] == "message_chunk":
            assert error["message"] not in frame["text"]
    assert frames[-1]["finish_reason"] == "error"


@pytest.mark.asyncio
async def test_client_abort_skips_persistence_and_logs_one_warning(monkeypatch, caplog):
    """A user interrupt sends no error frame, saves nothing, and leaves one warning."""
    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        abortable_coach_graph(["第一段", "第二段"], saved),
    )

    disconnect_checks = {"count": 0}

    async def disconnect_after_first_delta(self):
        disconnect_checks["count"] += 1
        return disconnect_checks["count"] > 1

    # httpx's ASGITransport never delivers http.disconnect while the app is still
    # producing the response, so the route seam is driven directly here.
    monkeypatch.setattr(Request, "is_disconnected", disconnect_after_first_delta)
    caplog.set_level(logging.WARNING, logger="app.api.coach")

    async with coach_client() as client:
        response = await post_stream(client, "别停")

    frames = decode_frames(response.text)
    assert [frame["type"] for frame in frames] == ["turn_started", "message_chunk"]
    assert visible_text(frames) == "第一段"
    assert saved == []
    assert response.headers["content-type"].startswith("text/event-stream")

    aborted_events = [
        record
        for record in caplog.records
        if getattr(record, "fields", {}).get("event") == EVENT_SSE_INTERRUPTED
    ]
    assert len(aborted_events) == 1
    assert aborted_events[0].levelno == logging.WARNING
    assert "别停" not in caplog.text
    assert "第一段" not in caplog.text


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated SQLite database for history replay tests."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'coach-stream.db'}",
        future=True,
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory
    await engine.dispose()


@asynccontextmanager
async def history_client(session_factory):
    """Client backed by the isolated database so auth and history run for real."""

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def auth_headers(user_id: int) -> dict[str, str]:
    """Build bearer auth headers for one persisted user."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_history_cleans_legacy_assistant_rows_at_read_time(session_factory):
    """Rows written before the cleaner existed replay as cleaned text, idempotently."""
    async with session_factory() as session:
        user = User(openid="coach-history-user", nickname="History", is_admin=False)
        session.add(user)
        await session.flush()
        session.add(ChatMessageRecord(user_id=user.id, role="user", content="今天练什么"))
        session.add(
            ChatMessageRecord(
                user_id=user.id,
                role="assistant",
                content=(
                    '```json\n{"reply": "bro，今天先练腿。", '
                    '"suggested_actions": []}\n```'
                ),
            )
        )
        session.add(
            ChatMessageRecord(user_id=user.id, role="assistant", content="先热身。")
        )
        await session.commit()
        user_id = user.id

    async with history_client(session_factory) as client:
        response = await client.get(
            f"/api/coach/{user_id}/history",
            headers=auth_headers(user_id),
        )

    assert response.status_code == 200
    messages = response.json()["messages"]
    assistant_texts = [item["content"] for item in messages if item["role"] == "assistant"]
    assert set(assistant_texts) == {"bro，今天先练腿。", "先热身。"}
    assert '{"reply"' not in response.text
    assert "```" not in response.text
    assert "suggested_actions" not in response.text
