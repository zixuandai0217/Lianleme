"""姿态会话 + 帧上行 + 周期切分的路由级测试（工单 40）。

只断言 HTTP 可观测行为与纯函数输出：会话契约、等待态、周期边界、质量门槛、
上限、鉴权/所有权、结束摘要、隐私（响应里没有关键点），以及「不成周期不产生
模型调用」这条成本闸门（用计数替身断言）。
"""

import datetime
import math
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.pose import get_pose_graph
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.services.ai.pose_graph import PoseGraph
from app.services.pose.segmentation import KNEE_CHAIN
from app.services.pose.session_store import (
    MAX_FRAMES_PER_SESSION,
    SESSION_TTL_SECONDS,
    PoseSessionStore,
    get_pose_session_store,
)

SESSIONS_URL = "/api/pose/sessions"
START_ANGLE = 175.0
BOTTOM_ANGLE = 90.0


# --- 合成关键点序列 ---------------------------------------------------------


def _leg_points(angle: float, x_center: float):
    """按膝角构造髋/膝/踝三点（180° = 完全伸直）。"""
    delta = math.radians(180.0 - angle)
    hip = (x_center, 0.40)
    knee = (x_center, 0.55)
    ankle = (knee[0] + 0.15 * math.sin(delta), knee[1] + 0.15 * math.cos(delta))
    return hip, knee, ankle


def _frame(
    t_ms: int,
    angle: float,
    *,
    visibility: float = 0.95,
    person_count: int | None = 1,
    x_shift: float = 0.0,
) -> dict:
    """构造一帧帧批载荷（33 点关键点，可只给运动相关点赋值）。"""
    keypoints = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.95} for _ in range(33)]
    for indices, x_center in ((KNEE_CHAIN.left, 0.45), (KNEE_CHAIN.right, 0.55)):
        for index, point in zip(indices, _leg_points(angle, x_center)):
            keypoints[index] = {
                "x": point[0] + x_shift,
                "y": point[1],
                "z": 0.0,
                "visibility": visibility,
            }
    frame = {"t_ms": t_ms, "keypoints": keypoints}
    if person_count is not None:
        frame["person_count"] = person_count
    return frame


def _angle_at(t_ms: int, segments: list[tuple[int, float, float]]) -> float:
    cursor = 0
    for duration, start, end in segments:
        if t_ms <= cursor + duration:
            if duration <= 0:
                return end
            return start + (end - start) * ((t_ms - cursor) / duration)
        cursor += duration
    return segments[-1][2]


def _sequence(segments, *, fps: int = 4, **frame_kwargs) -> list[dict]:
    interval = max(1, round(1000 / fps))
    total = sum(duration for duration, _, _ in segments)
    return [
        _frame(t_ms, _angle_at(t_ms, segments), **frame_kwargs)
        for t_ms in range(0, total + 1, interval)
    ]


def _rep_segments(
    *,
    hold_ms: int = 600,
    rep_ms: int = 2000,
    tail_ms: int = 600,
    reps: int = 1,
    gap_ms: int = 600,
) -> list[tuple[int, float, float]]:
    down = rep_ms // 2
    up = rep_ms - down
    segments: list[tuple[int, float, float]] = []
    for index in range(reps):
        segments.append((hold_ms, START_ANGLE, START_ANGLE))
        segments.append((down, START_ANGLE, BOTTOM_ANGLE))
        segments.append((up, BOTTOM_ANGLE, START_ANGLE))
        if index < reps - 1:
            segments.append((gap_ms, START_ANGLE, START_ANGLE))
    segments.append((tail_ms, START_ANGLE, START_ANGLE))
    return segments


def _batches(frames: list[dict], size: int) -> list[list[dict]]:
    return [frames[index:index + size] for index in range(0, len(frames), size)]


# --- 替身与夹具 -------------------------------------------------------------


class FakeClock:
    """可拨动的墙钟：用来验证 TTL 与续期。"""

    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CountingPoseGraph(PoseGraph):
    """计数替身：断言每个帧批都走了接帧 + 切分，且没有模型调用。"""

    def __init__(self) -> None:
        super().__init__()
        self.ingest_calls = 0
        self.segment_calls = 0

    def ingest_frames(self, window, new_frames):
        self.ingest_calls += 1
        return super().ingest_frames(window, new_frames)

    def segment_cycle(self, frames, *, camera_view="front"):
        self.segment_calls += 1
        return super().segment_cycle(frames, camera_view=camera_view)


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pose-sessions.db'}", future=True
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_users(session_factory):
    async with session_factory() as session:
        normal = User(openid="pose-user-1", nickname="Pose One", is_admin=False)
        other = User(openid="pose-user-2", nickname="Pose Two", is_admin=False)
        session.add_all([normal, other])
        await session.commit()
        await session.refresh(normal)
        await session.refresh(other)
        return {"normal": normal, "other": other}


@pytest_asyncio.fixture
async def clock():
    return FakeClock()


@pytest_asyncio.fixture
async def store(clock):
    return PoseSessionStore(clock=clock)


@pytest_asyncio.fixture
async def graph():
    return CountingPoseGraph()


@pytest_asyncio.fixture
async def client(session_factory, store, graph):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_pose_session_store] = lambda: store
    app.dependency_overrides[get_pose_graph] = lambda: graph

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


def _auth_headers(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_session(client: AsyncClient, user_id: int, **payload) -> dict:
    response = await client.post(
        SESSIONS_URL, json=payload or None, headers=_auth_headers(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _push(
    client: AsyncClient,
    user_id: int,
    session_id: str,
    frames: list[dict],
):
    return await client.post(
        f"{SESSIONS_URL}/{session_id}/frames",
        json={"frames": frames},
        headers=_auth_headers(user_id),
    )


def _assert_no_keypoints(value) -> None:
    """隐私断言：任何响应体里都不允许出现关键点或媒体字段。"""
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in {"keypoints", "image", "image_base64", "video", "video_base64"}
            _assert_no_keypoints(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_keypoints(item)


# --- 会话契约 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_contract(client, seeded_users, clock):
    user = seeded_users["normal"]

    response = await client.post(SESSIONS_URL, headers=_auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"].startswith("pose_")
    assert body["ttl_seconds"] == 1800
    assert body["upload_interval_ms"] == 200
    assert body["camera_hint"]
    expires_at = datetime.datetime.fromisoformat(body["expires_at"])
    assert expires_at == datetime.datetime.fromtimestamp(
        clock.now + body["ttl_seconds"], tz=datetime.timezone.utc
    )


@pytest.mark.asyncio
async def test_create_session_requires_auth(client):
    response = await client.post(SESSIONS_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_frames_require_auth(client):
    response = await client.post(
        f"{SESSIONS_URL}/pose_unknown/frames", json={"frames": [_frame(0, START_ANGLE)]}
    )

    assert response.status_code == 401


# --- 等待态与周期 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_incomplete_cycle_keeps_waiting_without_model_calls(
    client, seeded_users, graph
):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    # 只推送到下蹲途中：没有回到起始姿态，绝不构成周期；person_count 走默认值 1。
    frames = _sequence(
        [(600, START_ANGLE, START_ANGLE), (1000, START_ANGLE, BOTTOM_ANGLE)],
        person_count=None,
    )

    response = await _push(client, user.id, session["session_id"], frames)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == len(frames)
    assert body["cycle_state"] == "waiting"
    assert body["cycles"] == []
    assert body["cycles_count"] == 0
    assert graph.segment_calls == 1
    assert graph.ingest_calls == 1
    assert graph.model_calls == 0
    assert "score" not in response.text


@pytest.mark.asyncio
async def test_complete_cycle_reports_identifier_and_bounds(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    frames = _sequence(_rep_segments())

    response = await _push(client, user.id, session["session_id"], frames)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cycle_state"] == "completed"
    assert body["cycles_count"] == 1
    cycle = body["cycles"][0]
    assert cycle["cycle_id"].startswith("cyc_")
    assert cycle["end_ms"] > cycle["start_ms"]
    assert 1500 <= cycle["duration_ms"] <= 6000
    assert cycle["evaluable"] is True
    assert cycle["score"] is None
    assert cycle["issues"] == []


@pytest.mark.asyncio
async def test_two_cycles_across_incremental_batches(client, seeded_users, graph):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    frames = _sequence(_rep_segments(reps=2))

    cycles: list[dict] = []
    batches = _batches(frames, 3)
    for batch in batches:
        response = await _push(client, user.id, session["session_id"], batch)
        assert response.status_code == 200, response.text
        cycles.extend(response.json()["cycles"])

    assert len(cycles) == 2
    assert len({cycle["cycle_id"] for cycle in cycles}) == 2
    for cycle in cycles:
        assert 1500 <= cycle["duration_ms"] <= 6000
    assert graph.segment_calls == len(batches)

    result = await client.get(
        f"{SESSIONS_URL}/{session['session_id']}/result",
        headers=_auth_headers(user.id),
    )
    assert result.status_code == 200
    body = result.json()
    assert body["cycles_count"] == 2
    assert body["cycle_state"] == "completed"
    assert body["status"] == "active"
    assert len(body["cycles"]) == 2


@pytest.mark.asyncio
async def test_side_camera_view_is_accepted_and_segments_cycle(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id, camera_view="side")
    assert session["camera_view"] == "side"

    response = await _push(
        client, user.id, session["session_id"], _sequence(_rep_segments())
    )

    assert response.status_code == 200
    assert response.json()["cycles_count"] == 1


@pytest.mark.asyncio
async def test_too_short_cycle_does_not_form(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)

    response = await _push(
        client, user.id, session["session_id"], _sequence(_rep_segments(rep_ms=600))
    )

    assert response.status_code == 200
    assert response.json()["cycles"] == []
    assert response.json()["cycle_state"] == "waiting"


# --- 质量门槛 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_visibility_cycle_is_not_evaluable_without_model_calls(
    client, seeded_users, graph
):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)

    response = await _push(
        client,
        user.id,
        session["session_id"],
        _sequence(_rep_segments(), visibility=0.4),
    )

    assert response.status_code == 200
    cycle = response.json()["cycles"][0]
    assert cycle["evaluable"] is False
    assert "low_visibility" in cycle["reasons"]
    assert cycle["camera_hint"]
    assert cycle["score"] is None
    assert cycle["issues"] == []
    assert graph.model_calls == 0


@pytest.mark.asyncio
async def test_multiple_persons_cycle_is_not_evaluable(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)

    response = await _push(
        client,
        user.id,
        session["session_id"],
        _sequence(_rep_segments(), person_count=2),
    )

    assert response.status_code == 200
    cycle = response.json()["cycles"][0]
    assert cycle["evaluable"] is False
    assert "multiple_persons" in cycle["reasons"]
    assert cycle["camera_hint"]


@pytest.mark.asyncio
async def test_out_of_frame_cycle_is_not_evaluable(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)

    response = await _push(
        client,
        user.id,
        session["session_id"],
        _sequence(_rep_segments(), x_shift=-0.60),
    )

    assert response.status_code == 200
    cycle = response.json()["cycles"][0]
    assert cycle["evaluable"] is False
    assert "out_of_frame" in cycle["reasons"]


# --- 上限与顺序 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_too_large_is_rejected(client, seeded_users, graph):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    frames = [_frame(t_ms, START_ANGLE) for t_ms in range(0, 61 * 250, 250)]

    response = await _push(client, user.id, session["session_id"], frames)

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["code"] == "pose_batch_too_large"
    assert detail["message"]
    assert graph.segment_calls == 0

    result = await client.get(
        f"{SESSIONS_URL}/{session['session_id']}/result",
        headers=_auth_headers(user.id),
    )
    assert result.json()["cycles_count"] == 0


@pytest.mark.asyncio
async def test_session_frame_limit_is_enforced(client, seeded_users, store):
    user = seeded_users["normal"]
    store.max_frames_per_session = 20
    session = await _create_session(client, user.id)
    session_id = session["session_id"]

    first = await _push(client, user.id, session_id, [_frame(t_ms, START_ANGLE)
                                                     for t_ms in range(0, 12 * 250, 250)])
    assert first.status_code == 200
    assert first.json()["total_frames"] == 12

    second = await _push(client, user.id, session_id, [_frame(t_ms, START_ANGLE)
                                                       for t_ms in range(12 * 250, 24 * 250, 250)])
    assert second.status_code == 413
    assert second.json()["detail"]["code"] == "pose_session_frame_limit"
    assert second.json()["detail"]["message"]

    third = await _push(client, user.id, session_id, [_frame(t_ms, START_ANGLE)
                                                      for t_ms in range(24 * 250, 29 * 250, 250)])
    assert third.status_code == 200
    assert third.json()["total_frames"] == 17


@pytest.mark.asyncio
async def test_out_of_order_frames_are_rejected(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    session_id = session["session_id"]

    first = await _push(client, user.id, session_id,
                        [_frame(0, START_ANGLE), _frame(250, START_ANGLE),
                         _frame(500, START_ANGLE)])
    assert first.status_code == 200

    backwards = await _push(client, user.id, session_id, [_frame(250, START_ANGLE)])
    assert backwards.status_code == 422
    assert backwards.json()["detail"]["code"] == "pose_frames_out_of_order"

    # 批次内部乱序同样拒绝，且不会部分写入。
    internal = await _push(client, user.id, session_id,
                           [_frame(750, START_ANGLE), _frame(700, START_ANGLE)])
    assert internal.status_code == 422

    recovered = await _push(client, user.id, session_id, [_frame(750, START_ANGLE)])
    assert recovered.status_code == 200


# --- 鉴权、所有权、过期、并发上限 -------------------------------------------


@pytest.mark.asyncio
async def test_other_users_session_is_forbidden(client, seeded_users):
    owner = seeded_users["normal"]
    intruder = seeded_users["other"]
    session = await _create_session(client, owner.id)

    response = await _push(client, intruder.id, session["session_id"],
                           [_frame(0, START_ANGLE)])

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "pose_session_forbidden"


@pytest.mark.asyncio
async def test_unknown_session_is_not_found(client, seeded_users):
    user = seeded_users["normal"]

    response = await client.get(
        f"{SESSIONS_URL}/pose_does_not_exist/result", headers=_auth_headers(user.id)
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "pose_session_not_found"


@pytest.mark.asyncio
async def test_expired_session_is_not_found(client, seeded_users, clock):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)

    clock.advance(SESSION_TTL_SECONDS + 1)

    response = await client.get(
        f"{SESSIONS_URL}/{session['session_id']}/result", headers=_auth_headers(user.id)
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "pose_session_not_found"


@pytest.mark.asyncio
async def test_ttl_refreshes_on_each_accepted_request(client, seeded_users, clock):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    session_id = session["session_id"]

    clock.advance(SESSION_TTL_SECONDS - 10)
    keep_alive = await client.get(
        f"{SESSIONS_URL}/{session_id}/result", headers=_auth_headers(user.id)
    )
    assert keep_alive.status_code == 200

    clock.advance(SESSION_TTL_SECONDS - 10)
    still_alive = await client.get(
        f"{SESSIONS_URL}/{session_id}/result", headers=_auth_headers(user.id)
    )
    assert still_alive.status_code == 200

    clock.advance(SESSION_TTL_SECONDS + 1)
    expired = await client.get(
        f"{SESSIONS_URL}/{session_id}/result", headers=_auth_headers(user.id)
    )
    assert expired.status_code == 404


@pytest.mark.asyncio
async def test_third_concurrent_session_limit_is_rejected(client, seeded_users):
    user = seeded_users["normal"]
    created = [await _create_session(client, user.id) for _ in range(3)]
    assert len(created) == 3

    fourth = await client.post(SESSIONS_URL, headers=_auth_headers(user.id))

    assert fourth.status_code == 429
    detail = fourth.json()["detail"]
    assert detail["code"] == "pose_session_limit"
    assert "3" in detail["message"]

    finished = await client.post(
        f"{SESSIONS_URL}/{created[0]['session_id']}/finish",
        headers=_auth_headers(user.id),
    )
    assert finished.status_code == 200
    replacement = await client.post(SESSIONS_URL, headers=_auth_headers(user.id))
    assert replacement.status_code == 200


# --- 结束会话 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_finish_returns_summary_and_blocks_later_access(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    session_id = session["session_id"]
    await _push(client, user.id, session_id, _sequence(_rep_segments()))

    finish = await client.post(
        f"{SESSIONS_URL}/{session_id}/finish", headers=_auth_headers(user.id)
    )
    assert finish.status_code == 200
    summary = finish.json()
    assert summary["cycles_count"] == 1
    assert summary["evaluable_cycles"] == 1
    assert summary["not_evaluable_cycles"] == 0
    assert summary["avg_quality"] == 0.0
    assert summary["issues_histogram"] == {}
    assert summary["quality_available"] is False
    _assert_no_keypoints(summary)

    frames_after = await _push(client, user.id, session_id, [_frame(9000, START_ANGLE)])
    assert frames_after.status_code == 409
    assert frames_after.json()["detail"]["code"] == "pose_session_finished"

    result_after = await client.get(
        f"{SESSIONS_URL}/{session_id}/result", headers=_auth_headers(user.id)
    )
    assert result_after.status_code == 409
    assert result_after.json()["detail"]["code"] == "pose_session_finished"

    # 重复结束幂等：客户端重试不会把会话状态改坏。
    again = await client.post(
        f"{SESSIONS_URL}/{session_id}/finish", headers=_auth_headers(user.id)
    )
    assert again.status_code == 200
    assert again.json()["cycles_count"] == 1


@pytest.mark.asyncio
async def test_responses_never_contain_keypoints(client, seeded_users):
    user = seeded_users["normal"]
    create = await client.post(SESSIONS_URL, headers=_auth_headers(user.id))
    session_id = create.json()["session_id"]

    pushed = await _push(client, user.id, session_id, _sequence(_rep_segments()))
    result = await client.get(
        f"{SESSIONS_URL}/{session_id}/result", headers=_auth_headers(user.id)
    )
    finish = await client.post(
        f"{SESSIONS_URL}/{session_id}/finish", headers=_auth_headers(user.id)
    )

    for response in (create, pushed, result, finish):
        assert response.status_code == 200
        _assert_no_keypoints(response.json())


# --- 载荷校验 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_media_payload_fields_are_rejected(client, seeded_users, graph):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    session_id = session["session_id"]

    frame_with_image = _frame(0, START_ANGLE)
    frame_with_image["image_base64"] = "data:image/jpeg;base64,AAAA"
    response = await _push(client, user.id, session_id, [frame_with_image])
    assert response.status_code == 422
    assert "pose_media_payload_rejected" in response.text

    response = await client.post(
        f"{SESSIONS_URL}/{session_id}/frames",
        json={"frames": [_frame(0, START_ANGLE)], "video_base64": "AAAA"},
        headers=_auth_headers(user.id),
    )
    assert response.status_code == 422
    assert "pose_media_payload_rejected" in response.text
    assert graph.segment_calls == 0


@pytest.mark.asyncio
async def test_non_finite_keypoint_is_rejected(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    frame = _frame(0, START_ANGLE)
    frame["keypoints"][23]["x"] = float("nan")

    response = await _push(client, user.id, session["session_id"], [frame])

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "pose_keypoint_invalid"


@pytest.mark.asyncio
async def test_visibility_out_of_range_is_rejected(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    frame = _frame(0, START_ANGLE)
    frame["keypoints"][23]["visibility"] = 1.5

    response = await _push(client, user.id, session["session_id"], [frame])

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "pose_keypoint_invalid"


@pytest.mark.asyncio
async def test_too_many_keypoints_is_rejected(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    frame = _frame(0, START_ANGLE)
    frame["keypoints"].append({"x": 0.1, "y": 0.1, "z": 0.0, "visibility": 1.0})

    response = await _push(client, user.id, session["session_id"], [frame])

    assert response.status_code == 422


def test_session_store_defaults():
    """上限与 TTL 是服务端常量，不依赖配置注入。"""
    assert SESSION_TTL_SECONDS == 1800
    assert MAX_FRAMES_PER_SESSION == 3600
    store = PoseSessionStore()
    assert store.ttl_seconds == SESSION_TTL_SECONDS
    assert store.max_frames_per_session == MAX_FRAMES_PER_SESSION
    assert store.max_sessions_per_user == 3
