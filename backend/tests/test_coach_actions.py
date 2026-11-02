"""服务端快捷动作与教练状态的路由/规划器契约测试（工单 18）。

覆盖：
- 纯规划器的确定性、上下文差异、动作字段完整性与四种状态推导；
- 路由帧顺序：turn_started → chunks → state → actions → done，且各恰好一次；
- 非流式接口与流式接口来自同一规划环节；
- 动作快照与状态随助手消息入库，历史接口原样带回；旧记录缺少快照时降级为空。
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import coach as coach_api
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import require_current_user_api_key
from app.main import app
from app.models.chat_message import ChatMessageRecord
from app.models.user import User
from app.services.ai import coach_graph as coach_graph_module
from app.services.ai.coach_graph import CoachGraph
from app.services.coach.planner import (
    GENERIC_ACTIONS,
    CoachContext,
    derive_coach_state,
    plan_coach_turn,
    plan_quick_actions,
)

USER_ID = 7
STREAM_URL = "/api/coach/chat/stream"
CHAT_URL = "/api/coach/chat"
COACH_STATES = {"guide", "count", "rest", "complete"}


def training_context(**overrides) -> CoachContext:
    """A training-day context with the user mid-exercise."""
    values = {
        "status": "training_day",
        "current_exercise": "深蹲",
        "exercise_completed_sets": 1,
        "exercise_total_sets": 4,
        "session_completed_sets": 3,
        "session_total_sets": 12,
        "rest_seconds": 90,
    }
    values.update(overrides)
    return CoachContext(**values)


# ── 纯规划器 ──


def test_contextual_actions_are_valid_and_differ_from_the_generic_fallback():
    """有当前动作/组数进度时，动作集与无上下文时的通用集不同且都非空。"""
    contextual = plan_quick_actions(training_context())
    generic = plan_quick_actions(CoachContext())

    assert 1 <= len(contextual) <= 4
    assert generic == list(GENERIC_ACTIONS)
    assert len(generic) == 4
    assert contextual != generic
    for action in contextual + generic:
        assert action.label.strip()
        assert action.prompt.strip()


def test_rest_day_and_no_plan_contexts_also_get_non_empty_actions():
    """恢复日与无计划都是可解析上下文，同样不能出现空按钮区。"""
    rest = plan_quick_actions(CoachContext(status="rest_day"))
    no_plan = plan_quick_actions(CoachContext(status="no_plan"))

    assert rest and no_plan
    assert rest != no_plan
    assert all(action.prompt.strip() for action in rest + no_plan)


def test_planner_accepts_a_plain_context_mapping():
    """直接调用规划器的调用方可以传 plain dict，不必构造 dataclass。"""
    assert plan_quick_actions({"status": "rest_day"}) == plan_quick_actions(
        CoachContext(status="rest_day")
    )
    assert derive_coach_state(
        {"status": "training_day", "current_exercise": "深蹲"}, "开始第2组"
    ) == "count"


def test_action_planning_is_deterministic():
    """相同上下文反复规划得到完全相同的动作列表（无随机、无模型参与）。"""
    context = training_context()
    plans = [plan_quick_actions(context) for _ in range(5)]

    assert all(plan == plans[0] for plan in plans)
    assert plan_coach_turn(context, "第2组做完了").actions == plans[0]


@pytest.mark.parametrize(
    ("context", "message", "expected"),
    [
        (CoachContext(), "今天练什么", "guide"),
        (training_context(), "今天练什么", "guide"),
        (training_context(), "开始第2组", "count"),
        (training_context(), "第2组做完了", "rest"),
        (training_context(), "组间休息一下", "rest"),
        (training_context(exercise_completed_sets=3), "最后一组做完", "complete"),
        (training_context(exercise_completed_sets=4), "随便聊聊", "complete"),
        (training_context(finished=True), "收工", "complete"),
    ],
)
def test_coach_state_is_derived_from_context_and_message(context, message, expected):
    """四种状态都由服务端规则推导；缺省回落 guide。"""
    state = derive_coach_state(context, message)
    assert state == expected
    assert state in COACH_STATES


def test_plan_coach_turn_returns_state_and_actions_together():
    """路由只需要一次调用就能拿到本轮状态与动作。"""
    plan = plan_coach_turn(training_context(), "第2组做完了")

    assert plan.coach_state == "rest"
    assert plan.actions == plan_quick_actions(training_context())


# ── 路由层 ──


def decode_frames(body: str) -> list[dict]:
    """Decode the SSE body into typed JSON frames."""
    frames: list[dict] = []
    for block in body.split("\n\n"):
        if not block:
            continue
        line = block.strip()
        assert line.startswith("data: ")
        frames.append(json.loads(line[len("data: "):]))
    return frames


@asynccontextmanager
async def coach_client():
    """App client wired to fake auth and a placeholder database."""

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


def scripted_coach_graph(tokens: list[str], saved: list[tuple]):
    """A fake graph that replays tokens and records the persistence snapshot."""

    class ScriptedCoachGraph:
        def __init__(self, user_id: int, db: object):
            self.user_id = user_id
            self.db = db

        async def stream_chat(self, message: str, context: dict):
            for token in tokens:
                yield token

        async def save_turn(
            self, message: str, reply: str, *, actions=None, coach_state=None
        ):
            saved.append((message, reply, actions, coach_state))

    return ScriptedCoachGraph


async def post_stream(client: AsyncClient, message: str, **context):
    """Post one coach turn with optional training context."""
    return await client.post(
        STREAM_URL,
        json={"user_id": USER_ID, "message": message, **context},
    )


def frame_types(frames: list[dict]) -> list[str]:
    return [frame["type"] for frame in frames]


@pytest.mark.asyncio
async def test_stream_emits_exactly_one_state_and_actions_before_done(monkeypatch):
    """收尾前恰好一次状态帧与一次动作帧，顺序固定。"""
    saved: list[tuple] = []
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        scripted_coach_graph(["bro，接着干。"], saved),
    )

    async with coach_client() as client:
        response = await post_stream(
            client,
            "第2组做完了",
            current_exercise="深蹲",
            completed_sets=1,
            total_sets=4,
        )

    frames = decode_frames(response.text)
    assert frame_types(frames) == [
        "turn_started",
        "message_chunk",
        "state",
        "actions",
        "done",
    ]
    assert frame_types(frames).count("state") == 1
    assert frame_types(frames).count("actions") == 1
    assert frames[-2]["type"] == "actions"
    assert frames[-3]["type"] == "state"
    assert frames[-3]["coach_state"] == "rest"
    actions = frames[-2]["actions"]
    assert 1 <= len(actions) <= 4
    assert all(item["label"].strip() and item["prompt"].strip() for item in actions)
    assert saved[0][0] == "第2组做完了"
    assert saved[0][1] == "bro，接着干。"
    assert [action.model_dump() for action in saved[0][2]] == actions
    assert saved[0][3] == "rest"


@pytest.mark.asyncio
async def test_stream_without_today_context_uses_generic_actions(monkeypatch):
    """没有今日上下文时仍下发非空通用动作，状态缺省为 guide。"""
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        scripted_coach_graph(["ok"], []),
    )

    async with coach_client() as client:
        response = await post_stream(client, "今天练什么")

    frames = decode_frames(response.text)
    state = next(frame for frame in frames if frame["type"] == "state")
    actions = next(frame for frame in frames if frame["type"] == "actions")["actions"]
    assert state["coach_state"] == "guide"
    assert actions == [action.model_dump() for action in GENERIC_ACTIONS]


@pytest.mark.asyncio
async def test_same_context_and_message_produce_identical_actions_and_state(monkeypatch):
    """相同上下文 + 相同消息重复请求，动作与状态不漂移。"""
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        scripted_coach_graph(["ok"], []),
    )

    async with coach_client() as client:
        first = await post_stream(
            client,
            "第2组做完了",
            current_exercise="深蹲",
            completed_sets=1,
            total_sets=4,
        )
        second = await post_stream(
            client,
            "第2组做完了",
            current_exercise="深蹲",
            completed_sets=1,
            total_sets=4,
        )

    def planned(body: str) -> tuple[str, list[dict]]:
        frames = decode_frames(body)
        state = next(frame["coach_state"] for frame in frames if frame["type"] == "state")
        actions = next(frame["actions"] for frame in frames if frame["type"] == "actions")
        return state, actions

    assert planned(first.text) == planned(second.text)


@pytest.mark.asyncio
async def test_non_stream_returns_the_same_actions_and_state_as_the_stream(monkeypatch):
    """非流式接口复用同一规划器：动作列表与状态必须与流式一致。"""
    saved_messages: list[tuple[str, str]] = []

    async def fake_load_history(self, db):
        return []

    async def fake_save_message(self, db, role, content):
        saved_messages.append((role, content))

    class FakeLLM:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="ok")

    async def fake_get_client(self, user_id, model_type, streaming=False):
        return FakeLLM()

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc_info):
            return False

    async def fake_stream_chat(self, message, context):
        yield "ok"

    async def fake_save_turn(self, message, reply, *, actions=None, coach_state=None):
        saved_messages.append(("assistant", reply))

    monkeypatch.setattr(CoachGraph, "_load_history", fake_load_history)
    monkeypatch.setattr(CoachGraph, "_save_message", fake_save_message)
    monkeypatch.setattr(CoachGraph, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(CoachGraph, "save_turn", fake_save_turn)
    monkeypatch.setattr(coach_graph_module, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(coach_api, "CoachGraph", CoachGraph)
    from app.services.ai.llm_factory import LLMClientFactory

    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)

    payload = {
        "user_id": USER_ID,
        "message": "第2组做完了",
        "current_exercise": "深蹲",
        "completed_sets": 1,
        "total_sets": 4,
    }
    async with coach_client() as client:
        streamed = await client.post(STREAM_URL, json=payload)
        plain = await client.post(CHAT_URL, json=payload)

    stream_frames = decode_frames(streamed.text)
    stream_state = next(
        frame["coach_state"] for frame in stream_frames if frame["type"] == "state"
    )
    stream_actions = next(
        frame["actions"] for frame in stream_frames if frame["type"] == "actions"
    )
    body = plain.json()
    assert body["reply"] == "ok"
    assert body["coach_state"] == stream_state
    assert body["quick_actions"] == stream_actions
    assert body["suggested_actions"] == [item["prompt"] for item in stream_actions]


# ── 持久化与历史回放 ──


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Isolated SQLite database for history round-trip tests."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'coach-actions.db'}",
        future=True,
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@asynccontextmanager
async def history_client(session_factory):
    """Client whose database dependency and auth run for real."""

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
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_stream_persists_snapshot_and_history_returns_it(monkeypatch, session_factory):
    """流式一轮写入动作/状态，历史接口原样带回同一份快照。"""
    async def fake_stream_chat(self, message, context):
        yield "bro，接着干。"

    class SessionContext:
        def __init__(self):
            self.session = None

        async def __aenter__(self):
            self.session = session_factory()
            return self.session

        async def __aexit__(self, *exc_info):
            if self.session is not None:
                await self.session.close()
            return False

    monkeypatch.setattr(CoachGraph, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(coach_graph_module, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(coach_api, "CoachGraph", CoachGraph)

    async with session_factory() as session:
        user = User(
            id=USER_ID,
            openid=f"coach-actions-{uuid4().hex}",
            nickname="Actions",
            is_admin=False,
        )
        session.add(user)
        await session.commit()

    async with coach_client() as client:
        # 路由的上下文解析用假 DB，会回落到请求上下文；这正是本测试要的快照。
        response = await client.post(
            STREAM_URL,
            json={
                "user_id": USER_ID,
                "message": "第2组做完了",
                "current_exercise": "深蹲",
                "completed_sets": 1,
                "total_sets": 4,
            },
        )

    frames = decode_frames(response.text)
    expected_state = next(
        frame["coach_state"] for frame in frames if frame["type"] == "state"
    )
    expected_actions = next(
        frame["actions"] for frame in frames if frame["type"] == "actions"
    )

    async with history_client(session_factory) as client:
        history = await client.get(
            f"/api/coach/{USER_ID}/history",
            headers=auth_headers(USER_ID),
        )

    assert history.status_code == 200
    messages = history.json()["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "bro，接着干。"
    assert messages[1]["actions"] == expected_actions
    assert messages[1]["coach_state"] == expected_state


@pytest.mark.asyncio
async def test_history_returns_snapshot_and_degrades_when_it_is_missing(
    monkeypatch, session_factory
):
    """有快照的助手消息带回动作；旧消息 return 空列表 / None，不报错。"""
    async with session_factory() as session:
        user = User(openid=f"coach-history-{uuid4().hex}", nickname="History", is_admin=False)
        session.add(user)
        await session.flush()
        session.add(
            ChatMessageRecord(
                user_id=user.id,
                role="assistant",
                content="先热身。",
                actions=[{"label": "完成这组", "prompt": "我完成了深蹲第2组"}],
                coach_state="count",
            )
        )
        session.add(
            ChatMessageRecord(user_id=user.id, role="assistant", content="旧消息")
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
    assert messages[0]["actions"] == [
        {"label": "完成这组", "prompt": "我完成了深蹲第2组"}
    ]
    assert messages[0]["coach_state"] == "count"
    assert messages[1]["actions"] == []
    assert messages[1]["coach_state"] is None
