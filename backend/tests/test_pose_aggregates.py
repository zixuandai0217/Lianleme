"""姿态隐私边界与聚合摘要的路由级测试（工单 43）。

覆盖：结束会话落一条数值聚合（幂等）、聚合列表/详情/删除的所有权与稳定错误码、
删除后不可重算、伤病摘要的数值口径、四个会话响应与聚合响应的隐私断言，以及
结构化日志里没有坐标/角度序列。

测试只断言 HTTP 可观测行为与数据库里的聚合行，不读取任何关键点坐标。
"""

import datetime
import json
import logging
import math
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.pose import get_pose_graph
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.logging import StructuredJsonFormatter
from app.main import app
from app.models.pose_aggregate import PoseQualityAggregate
from app.models.user import User
from app.services.ai.pose_graph import PoseGraph
from app.services.pose.segmentation import KNEE_CHAIN
from app.services.pose.session_store import PoseSessionStore, get_pose_session_store

SESSIONS_URL = "/api/pose/sessions"
AGGREGATES_URL = "/api/pose/aggregates"
INJURY_SUMMARY_URL = "/api/pose/injury-summary"
START_ANGLE = 175.0
BOTTOM_ANGLE = 90.0
VALGUS_INWARD = 0.05


# --- 合成关键点序列（与 test_pose_sessions 同一构造方式） --------------------


def _leg_points(angle: float, x_center: float):
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


def _rep_segments(*, hold_ms: int = 600, rep_ms: int = 2000, tail_ms: int = 600):
    down = rep_ms // 2
    up = rep_ms - down
    return [
        (hold_ms, START_ANGLE, START_ANGLE),
        (down, START_ANGLE, BOTTOM_ANGLE),
        (up, BOTTOM_ANGLE, START_ANGLE),
        (tail_ms, START_ANGLE, START_ANGLE),
    ]


def _valgus_sequence() -> list[dict]:
    frames = _sequence(_rep_segments())
    for frame in frames:
        keypoints = frame["keypoints"]
        keypoints[KNEE_CHAIN.left[1]]["x"] += VALGUS_INWARD
        keypoints[KNEE_CHAIN.right[1]]["x"] -= VALGUS_INWARD
    return frames


# --- 夹具 -------------------------------------------------------------------


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pose-aggregates.db'}", future=True
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_users(session_factory):
    async with session_factory() as session:
        normal = User(openid="pose-aggregate-1", nickname="Aggregate One", is_admin=False)
        other = User(openid="pose-aggregate-2", nickname="Aggregate Two", is_admin=False)
        session.add_all([normal, other])
        await session.commit()
        await session.refresh(normal)
        await session.refresh(other)
        return {"normal": normal, "other": other}


@pytest_asyncio.fixture
async def store():
    return PoseSessionStore()


@pytest_asyncio.fixture
async def client(session_factory, store):
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
    app.dependency_overrides[get_pose_graph] = lambda: PoseGraph()

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


async def _push(client: AsyncClient, user_id: int, session_id: str, frames: list[dict]):
    return await client.post(
        f"{SESSIONS_URL}/{session_id}/frames",
        json={"frames": frames},
        headers=_auth_headers(user_id),
    )


async def _finish(client: AsyncClient, user_id: int, session_id: str):
    return await client.post(
        f"{SESSIONS_URL}/{session_id}/finish", headers=_auth_headers(user_id)
    )


async def _finish_one_cycle(client: AsyncClient, user_id: int) -> dict:
    """跑一个膝内扣周期并结束；返回结束摘要（含 aggregate_id）。"""
    session = await _create_session(client, user_id)
    pushed = await _push(client, user_id, session["session_id"], _valgus_sequence())
    assert pushed.status_code == 200, pushed.text
    finished = await _finish(client, user_id, session["session_id"])
    assert finished.status_code == 200, finished.text
    return finished.json()


def _assert_no_keypoints(value) -> None:
    """任何响应体里都不允许出现关键点/媒体字段。"""
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in {"keypoints", "image", "image_base64", "video", "video_base64"}
            _assert_no_keypoints(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_keypoints(item)


def _assert_no_coordinate_arrays(value) -> None:
    """坐标序列的形状：>=3 个连续数值的数组，或带 x/y/z 的对象。"""
    if isinstance(value, dict):
        assert not {"x", "y", "z"} <= set(value), f"coordinate object leaked: {value}"
        for item in value.values():
            _assert_no_coordinate_arrays(item)
    elif isinstance(value, list):
        if len(value) >= 3 and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
        ):
            raise AssertionError(f"numeric coordinate-like array leaked: {value}")
        for item in value:
            _assert_no_coordinate_arrays(item)


# --- 聚合落库与结束摘要 ------------------------------------------------------


@pytest.mark.asyncio
async def test_finish_persists_one_numeric_aggregate(
    client, seeded_users, session_factory
):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    pushed = await _push(client, user.id, session["session_id"], _valgus_sequence())
    cycle = pushed.json()["cycles"][0]

    finish = await _finish(client, user.id, session["session_id"])

    assert finish.status_code == 200, finish.text
    summary = finish.json()
    assert summary["cycles_count"] == 1
    assert summary["evaluable_cycles"] == 1
    assert summary["not_evaluable_cycles"] == 0
    assert summary["not_evaluable_ratio"] == 0.0
    assert summary["avg_quality"] == cycle["score"]
    assert summary["quality_available"] is True
    assert isinstance(summary["aggregate_id"], int)

    async with session_factory() as db:
        rows = (await db.execute(select(PoseQualityAggregate))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == user.id
    assert row.session_id == session["session_id"]
    assert row.cycles_count == 1
    assert row.evaluable_cycles == 1
    assert row.not_evaluable_cycles == 0
    assert row.avg_quality == cycle["score"]
    assert row.issues_histogram == summary["issues_histogram"]
    assert row.model_calls == 0
    assert row.started_at is not None and row.finished_at is not None
    assert row.finished_at >= row.started_at
    # 聚合行只有数值/类型计数：没有坐标、没有帧、没有自由文本列。
    column_names = set(PoseQualityAggregate.__table__.columns.keys())
    assert not column_names & {"keypoints", "frames", "angles", "coordinates", "feedback"}

    listed = await client.get(AGGREGATES_URL, headers=_auth_headers(user.id))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == summary["aggregate_id"]
    assert item["session_id"] == session["session_id"]
    assert item["cycles_count"] == 1
    assert item["not_evaluable_ratio"] == 0.0
    _assert_no_keypoints(body)
    _assert_no_coordinate_arrays(body)

    detail = await client.get(
        f"{AGGREGATES_URL}/{summary['aggregate_id']}", headers=_auth_headers(user.id)
    )
    assert detail.status_code == 200
    assert detail.json() == item
    _assert_no_keypoints(detail.json())
    _assert_no_coordinate_arrays(detail.json())


@pytest.mark.asyncio
async def test_repeated_finish_returns_same_aggregate_without_second_write(
    client, seeded_users, session_factory
):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    await _push(client, user.id, session["session_id"], _valgus_sequence())

    first = await _finish(client, user.id, session["session_id"])
    second = await _finish(client, user.id, session["session_id"])

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["aggregate_id"] == first.json()["aggregate_id"]
    assert second.json()["not_evaluable_ratio"] == first.json()["not_evaluable_ratio"]
    assert second.json()["cycles_count"] == first.json()["cycles_count"]

    async with session_factory() as db:
        count = (await db.execute(select(func.count(PoseQualityAggregate.id)))).scalar()
    assert count == 1

    listed = await client.get(AGGREGATES_URL, headers=_auth_headers(user.id))
    assert listed.json()["total"] == 1


@pytest.mark.asyncio
async def test_finish_reports_not_evaluable_ratio(client, seeded_users):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    await _push(
        client,
        user.id,
        session["session_id"],
        _sequence(_rep_segments(), visibility=0.4),
    )

    finish = await _finish(client, user.id, session["session_id"])

    assert finish.status_code == 200
    summary = finish.json()
    assert summary["cycles_count"] == 1
    assert summary["evaluable_cycles"] == 0
    assert summary["not_evaluable_cycles"] == 1
    assert summary["not_evaluable_ratio"] == 1.0
    assert summary["avg_quality"] == 0.0
    assert summary["quality_available"] is False

    detail = await client.get(
        f"{AGGREGATES_URL}/{summary['aggregate_id']}", headers=_auth_headers(user.id)
    )
    assert detail.status_code == 200
    assert detail.json()["not_evaluable_ratio"] == 1.0


# --- 所有权与稳定错误码 ------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_requires_auth(client):
    assert (await client.get(AGGREGATES_URL)).status_code == 401
    assert (await client.get(INJURY_SUMMARY_URL)).status_code == 401


@pytest.mark.asyncio
async def test_other_users_aggregate_is_forbidden_without_content(
    client, seeded_users
):
    owner = seeded_users["normal"]
    intruder = seeded_users["other"]
    summary = await _finish_one_cycle(client, owner.id)
    aggregate_id = summary["aggregate_id"]

    detail = await client.get(
        f"{AGGREGATES_URL}/{aggregate_id}", headers=_auth_headers(intruder.id)
    )
    assert detail.status_code == 403
    assert detail.json()["detail"]["code"] == "pose_aggregate_forbidden"
    assert "avg_quality" not in detail.text
    assert "issues_histogram" not in detail.text

    deleted = await client.delete(
        f"{AGGREGATES_URL}/{aggregate_id}", headers=_auth_headers(intruder.id)
    )
    assert deleted.status_code == 403
    assert deleted.json()["detail"]["code"] == "pose_aggregate_forbidden"

    still_there = await client.get(
        f"{AGGREGATES_URL}/{aggregate_id}", headers=_auth_headers(owner.id)
    )
    assert still_there.status_code == 200

    intruder_list = await client.get(AGGREGATES_URL, headers=_auth_headers(intruder.id))
    assert intruder_list.status_code == 200
    assert intruder_list.json() == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_unknown_aggregate_is_not_found_with_stable_code(client, seeded_users):
    user = seeded_users["normal"]

    detail = await client.get(f"{AGGREGATES_URL}/999999", headers=_auth_headers(user.id))
    assert detail.status_code == 404
    assert detail.json()["detail"]["code"] == "pose_aggregate_not_found"

    deleted = await client.delete(
        f"{AGGREGATES_URL}/999999", headers=_auth_headers(user.id)
    )
    assert deleted.status_code == 404
    assert deleted.json()["detail"]["code"] == "pose_aggregate_not_found"


# --- 删除语义 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_aggregate_and_cannot_be_recomputed(
    client, seeded_users, session_factory
):
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    await _push(client, user.id, session["session_id"], _valgus_sequence())
    summary = (await _finish(client, user.id, session["session_id"])).json()
    aggregate_id = summary["aggregate_id"]

    deleted = await client.delete(
        f"{AGGREGATES_URL}/{aggregate_id}", headers=_auth_headers(user.id)
    )
    assert deleted.status_code == 204

    detail = await client.get(
        f"{AGGREGATES_URL}/{aggregate_id}", headers=_auth_headers(user.id)
    )
    assert detail.status_code == 404
    assert detail.json()["detail"]["code"] == "pose_aggregate_not_found"

    listed = await client.get(AGGREGATES_URL, headers=_auth_headers(user.id))
    assert listed.json() == {"items": [], "total": 0}

    # 会话内存也随删除丢弃：重复结束拿不到会话，无法重算出被删的聚合。
    again = await _finish(client, user.id, session["session_id"])
    assert again.status_code == 404
    assert again.json()["detail"]["code"] == "pose_session_not_found"

    async with session_factory() as db:
        count = (await db.execute(select(func.count(PoseQualityAggregate.id)))).scalar()
    assert count == 0

    listed_after = await client.get(AGGREGATES_URL, headers=_auth_headers(user.id))
    assert listed_after.json() == {"items": [], "total": 0}


# --- 伤病摘要 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_injury_summary_is_numeric_and_aggregated(client, seeded_users):
    owner = seeded_users["normal"]
    intruder = seeded_users["other"]

    first = await _finish_one_cycle(client, owner.id)
    second = await _finish_one_cycle(client, owner.id)
    # 第三个会话只有一个不可评估周期：进分母，不进平均分。
    session = await _create_session(client, owner.id)
    await _push(
        client,
        owner.id,
        session["session_id"],
        _sequence(_rep_segments(), visibility=0.4),
    )
    third = (await _finish(client, owner.id, session["session_id"])).json()
    # 他人的聚合不得进入摘要。
    await _finish_one_cycle(client, intruder.id)

    response = await client.get(INJURY_SUMMARY_URL, headers=_auth_headers(owner.id))

    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["window_days"] == 14
    assert summary["sessions_covered"] == 3
    assert summary["training_days"] == 1
    assert summary["cycles_covered"] == 3
    assert summary["evaluable_cycles"] == 2
    assert summary["not_evaluable_cycles"] == 1
    assert summary["not_evaluable_ratio"] == round(1 / 3, 3)
    expected_avg = round((first["avg_quality"] + second["avg_quality"]) / 2, 1)
    assert summary["avg_quality"] == expected_avg
    assert summary["quality_available"] is True

    histogram: dict[str, int] = {}
    for item in (first, second, third):
        for issue_type, count in item["issues_histogram"].items():
            histogram[issue_type] = histogram.get(issue_type, 0) + count
    expected_top = [
        {"type": issue_type, "count": count}
        for issue_type, count in sorted(
            histogram.items(), key=lambda pair: (-pair[1], pair[0])
        )[:5]
    ]
    assert summary["top_issues"] == expected_top

    # 只读数值摘要：没有单次动作明细，也没有关键点/坐标。
    assert "sessions" not in summary
    assert "cycles" not in summary
    assert "session_id" not in summary
    _assert_no_keypoints(summary)
    _assert_no_coordinate_arrays(summary)
    for key, value in summary.items():
        if key == "top_issues":
            for issue in value:
                assert set(issue) == {"type", "count"}
                assert isinstance(issue["type"], str)
                assert isinstance(issue["count"], int)
        elif key == "quality_available":
            assert isinstance(value, bool)
        else:
            assert isinstance(value, (int, float)) and not isinstance(value, bool)

    intruder_summary = await client.get(
        INJURY_SUMMARY_URL, headers=_auth_headers(intruder.id)
    )
    assert intruder_summary.status_code == 200
    assert intruder_summary.json()["sessions_covered"] == 1


@pytest.mark.asyncio
async def test_injury_summary_respects_days_window(
    client, seeded_users, session_factory
):
    user = seeded_users["normal"]
    now = datetime.datetime.now(datetime.timezone.utc)
    async with session_factory() as db:
        db.add(
            PoseQualityAggregate(
                user_id=user.id,
                session_id="pose_recent_fixture",
                started_at=now - datetime.timedelta(hours=1),
                finished_at=now - datetime.timedelta(hours=1),
                cycles_count=2,
                evaluable_cycles=2,
                not_evaluable_cycles=0,
                avg_quality=7.5,
                issues_histogram={"knee_valgus": 2},
                model_calls=1,
            )
        )
        db.add(
            PoseQualityAggregate(
                user_id=user.id,
                session_id="pose_old_fixture",
                started_at=now - datetime.timedelta(days=40),
                finished_at=now - datetime.timedelta(days=40),
                cycles_count=4,
                evaluable_cycles=4,
                not_evaluable_cycles=0,
                avg_quality=3.0,
                issues_histogram={"trunk_lean": 4},
                model_calls=2,
            )
        )
        await db.commit()

    recent = await client.get(
        f"{INJURY_SUMMARY_URL}?days=14", headers=_auth_headers(user.id)
    )
    assert recent.status_code == 200
    body = recent.json()
    assert body["window_days"] == 14
    assert body["sessions_covered"] == 1
    assert body["cycles_covered"] == 2
    assert body["avg_quality"] == 7.5
    assert body["top_issues"] == [{"type": "knee_valgus", "count": 2}]

    wide = await client.get(
        f"{INJURY_SUMMARY_URL}?days=90", headers=_auth_headers(user.id)
    )
    assert wide.status_code == 200
    assert wide.json()["sessions_covered"] == 2
    assert wide.json()["cycles_covered"] == 6
    assert wide.json()["avg_quality"] == round((7.5 * 2 + 3.0 * 4) / 6, 1)

    invalid = await client.get(
        f"{INJURY_SUMMARY_URL}?days=0", headers=_auth_headers(user.id)
    )
    assert invalid.status_code == 422


# --- 隐私：日志 -------------------------------------------------------------


_ALLOWED_LOG_FIELDS = {
    "timestamp",
    "level",
    "event",
    "message",
    "request_id",
    "user_id",
    "session",
    "cycle_index",
    "duration_ms",
    "issue_types",
}
_FORBIDDEN_LOG_FIELD_PARTS = (
    "keypoint",
    "coordinate",
    "landmark",
    "angle",
    "frame",
    "point",
    "visibility",
)


def _normalized(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def _numeric_array_shaped(value) -> bool:
    if isinstance(value, (list, tuple)):
        if len(value) >= 3 and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
        ):
            return True
        return any(_numeric_array_shaped(item) for item in value)
    return False


@pytest.mark.asyncio
async def test_pose_logs_contain_no_coordinates_or_angles(client, seeded_users, caplog):
    caplog.set_level(logging.INFO)
    user = seeded_users["normal"]
    session = await _create_session(client, user.id)
    await _push(client, user.id, session["session_id"], _valgus_sequence())
    await _finish(client, user.id, session["session_id"])

    pose_payloads = [
        record.fields
        for record in caplog.records
        if getattr(record, "fields", None)
        and str(record.fields.get("event", "")).startswith("pose.")
    ]
    assert pose_payloads, "姿态链路必须留下可排障的结构化日志（但不能带坐标）"

    for payload in pose_payloads:
        for field_name, value in payload.items():
            assert field_name in _ALLOWED_LOG_FIELDS, (
                f"日志字段 {field_name!r} 不在允许列表内（只允许会话短标识/周期序号/耗时/问题类型）"
            )
            normalized = _normalized(field_name)
            assert not any(part in normalized for part in _FORBIDDEN_LOG_FIELD_PARTS)
            assert not _numeric_array_shaped(value), (
                f"日志字段 {field_name!r} 出现了坐标/角度数值序列：{value!r}"
            )
        if "issue_types" in payload:
            assert isinstance(payload["issue_types"], list)
            assert all(isinstance(item, str) for item in payload["issue_types"])
        assert session["session_id"] not in json.dumps(payload, ensure_ascii=False, default=str)

    # 日志里的会话标识是短哈希，不是可直接使用的完整会话 token。
    for payload in pose_payloads:
        if "session" in payload:
            assert len(str(payload["session"])) <= 12

    # 结构化格式化后的整行同样不能出现坐标字段或角度序列。
    formatter = StructuredJsonFormatter()
    rendered = "\n".join(formatter.format(record) for record in caplog.records)
    assert "keypoints" not in rendered
    assert "coordinates" not in rendered
    assert "angle" not in rendered.lower()
