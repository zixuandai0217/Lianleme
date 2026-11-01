"""Route-level contract tests for the AI coach SSE event stream.

The stream is a typed event stream: one JSON object per single-line ``data:``
frame. Tests drive the route through an ASGI client with auth/database
dependencies overridden and a fake CoachGraph, so no provider call is made.
"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import coach as coach_api
from app.core.database import get_db
from app.core.security import require_current_user_api_key
from app.main import app
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

        async def save_turn(self, message: str, reply: str):
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

    async def save_turn(self, message: str, reply: str):
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
    assert [frame["type"] for frame in frames] == ["turn_started", "error", "done"]
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
    assert payload["coach_state"] == "count"
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
