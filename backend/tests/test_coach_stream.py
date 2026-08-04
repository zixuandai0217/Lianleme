"""Regression tests for graceful AI coach streaming failures."""

from types import SimpleNamespace

import pytest

from app.api import coach as coach_api
from app.schemas.chat import ChatMessage


class FailingCoachGraph:
    """Simulate an upstream model failure after the SSE response starts."""

    def __init__(self, user_id: int, db: object):
        self.user_id = user_id
        self.db = db

    async def stream_chat(self, message: str, context: dict):
        """Raise the same class of failure produced by an invalid provider key."""
        if False:
            yield ""
        raise RuntimeError("invalid provider key")


@pytest.mark.asyncio
async def test_stream_returns_readable_error_and_done_marker(monkeypatch):
    """An upstream failure should complete SSE without aborting the connection."""
    monkeypatch.setattr(coach_api, "CoachGraph", FailingCoachGraph)
    response = await coach_api.chat_stream(
        ChatMessage(user_id=1, message="hello"),
        db=object(),
        current_user=SimpleNamespace(id=1),
    )

    chunks: list[str] = []
    try:
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        result = "".join(chunks)
    except Exception as exc:
        result = f"raised:{type(exc).__name__}"

    assert result == (
        "data: AI 服务暂时不可用，请检查 API Key 配置后重试。\n\n"
        "data: [DONE]\n\n"
    )
