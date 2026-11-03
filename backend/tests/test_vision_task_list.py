"""Route-level contract for the current-user analysis task list and history alignment.

The list endpoint is exercised through the real FastAPI routes, the real service
layer and an isolated SQLite database.  Assertions stay on externally observable
facts: HTTP status, response fields, ordering, paging behaviour and the status
projection.  The single-task polling endpoint is intentionally left untouched by
this ticket; its own contract lives in ``test_analysis_tasks.py``.
"""

from __future__ import annotations

import base64
import datetime
import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.storage import InMemoryStorage, get_storage
from app.main import app
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
from app.models.user import User

NOW = datetime.datetime.now(datetime.timezone.utc)

SUMMARY_FIELDS = {
    "task_id",
    "status",
    "error_code",
    "created_at",
    "updated_at",
    "history_record_id",
}

HISTORY_FIELDS = {
    "id",
    "image_thumbnail",
    "image_url",
    "thumbnail_url",
    "image_asset_id",
    "thumbnail_asset_id",
    "degraded",
    "result",
    "created_at",
    "task_id",
}


def _analysis_result(summary: str = "保持训练") -> dict:
    return {
        "body_type": "mesomorph",
        "body_fat_range": "15-20%",
        "weak_muscles": ["背"],
        "strengths": ["腿"],
        "muscle_scores": {"back": 6},
        "summary": summary,
    }


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'vision-task-list.db').as_posix()}",
        future=True,
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="task-list-owner", nickname="Owner")
        stranger = User(openid="task-list-stranger", nickname="Stranger")
        session.add_all([owner, stranger])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(stranger)
        return {"owner": owner, "stranger": stranger}


@pytest.fixture
def storage() -> InMemoryStorage:
    """Inline images are written through the storage port; never touch MinIO."""
    return InMemoryStorage()


@pytest_asyncio.fixture
async def client(session_factory, storage):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: storage
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


def auth_headers(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _seed_task(session_factory, user_id: int, task_id: str, **overrides) -> None:
    values = {
        "task_id": task_id,
        "user_id": user_id,
        "status": "pending",
        "stage": "queued",
        "attempt": 0,
        "progress": 0,
        "expires_at": NOW + datetime.timedelta(minutes=10),
    }
    values.update(overrides)
    async with session_factory() as session:
        session.add(AnalysisTask(**values))
        await session.commit()


async def _seed_record(
    session_factory, user_id: int, *, created_at: datetime.datetime | None = None
) -> int:
    values = {
        "user_id": user_id,
        "image_thumbnail": "bGVnYWN5LXRodW1ibmFpbA==",
        "result": _analysis_result(),
    }
    if created_at is not None:
        values["created_at"] = created_at
    async with session_factory() as session:
        record = BodyAnalysisRecord(**values)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def _list_tasks(client: AsyncClient, actor_id: int, **params) -> dict:
    response = await client.get(
        "/api/vision/tasks",
        params=params,
        headers=auth_headers(actor_id),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _collect_pages(
    client: AsyncClient,
    user_id: int,
    *,
    limit: int,
    status: str | None = None,
) -> list[dict]:
    """Walk every page, failing if the cursor never terminates."""
    items: list[dict] = []
    cursor: str | None = None
    for _ in range(50):
        params: dict[str, object] = {"limit": limit}
        if status is not None:
            params["status"] = status
        if cursor is not None:
            params["cursor"] = cursor
        page = await _list_tasks(client, user_id, **params)
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return items
    raise AssertionError("pagination did not terminate")


def _encode_cursor(payload: object) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# ── 鉴权与摘要形状 ──


@pytest.mark.asyncio
async def test_task_list_requires_authentication(client):
    response = await client.get("/api/vision/tasks")

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_task_list_returns_only_summary_fields_newest_first(client, session_factory, users):
    owner = users["owner"]
    await _seed_task(
        session_factory,
        owner.id,
        "task-older",
        created_at=NOW - datetime.timedelta(minutes=3),
        status="failed",
        stage="done",
        error_code="provider_timeout",
    )
    await _seed_task(
        session_factory,
        owner.id,
        "task-middle",
        created_at=NOW - datetime.timedelta(minutes=2),
        status="completed",
        stage="done",
    )
    await _seed_task(
        session_factory,
        owner.id,
        "task-newest",
        created_at=NOW - datetime.timedelta(minutes=1),
        status="processing",
        stage="vision",
    )

    body = await _list_tasks(client, owner.id)

    assert [item["task_id"] for item in body["items"]] == [
        "task-newest",
        "task-middle",
        "task-older",
    ]
    assert body["next_cursor"] is None

    failed = body["items"][2]
    assert failed["status"] == "failed"
    assert failed["error_code"] == "provider_timeout"
    assert failed["created_at"]
    assert failed["updated_at"]
    assert failed["history_record_id"] is None

    for item in body["items"]:
        assert set(item) == SUMMARY_FIELDS

    # Summary only: no result payload, no image content, no input profile.
    for forbidden in (
        "result",
        "body_type",
        "image_base64",
        "image_asset_id",
        "input_profile",
        "profile",
    ):
        assert forbidden not in body


# ── 状态投影与过滤 ──


@pytest.mark.asyncio
async def test_overdue_rows_are_reported_and_filtered_as_expired(
    client, session_factory, users
):
    owner = users["owner"]
    await _seed_task(
        session_factory,
        owner.id,
        "task-overdue-pending",
        status="pending",
        expires_at=NOW - datetime.timedelta(seconds=5),
    )
    await _seed_task(
        session_factory,
        owner.id,
        "task-overdue-processing",
        status="processing",
        stage="vision",
        expires_at=NOW - datetime.timedelta(seconds=5),
    )
    await _seed_task(session_factory, owner.id, "task-live", status="pending")
    await _seed_task(
        session_factory,
        owner.id,
        "task-written-expired",
        status="expired",
        stage="done",
        error_code="task_expired",
        expires_at=NOW - datetime.timedelta(minutes=1),
    )
    await _seed_task(
        session_factory,
        owner.id,
        "task-completed",
        status="completed",
        stage="done",
        expires_at=NOW - datetime.timedelta(minutes=1),
    )

    body = await _list_tasks(client, owner.id)
    by_id = {item["task_id"]: item["status"] for item in body["items"]}
    assert by_id["task-overdue-pending"] == "expired"
    assert by_id["task-overdue-processing"] == "expired"
    assert by_id["task-written-expired"] == "expired"
    assert by_id["task-live"] == "pending"
    # 已完成是终态：过期时间过了也不改写对外状态。
    assert by_id["task-completed"] == "completed"

    expired = await _list_tasks(client, owner.id, status="expired")
    assert {item["task_id"] for item in expired["items"]} == {
        "task-overdue-pending",
        "task-overdue-processing",
        "task-written-expired",
    }

    live = await _list_tasks(client, owner.id, status="pending")
    assert [item["task_id"] for item in live["items"]] == ["task-live"]

    processing = await _list_tasks(client, owner.id, status="processing")
    assert processing["items"] == []

    completed = await _list_tasks(client, owner.id, status="completed")
    assert [item["task_id"] for item in completed["items"]] == ["task-completed"]

    failed = await _list_tasks(client, owner.id, status="failed")
    assert failed["items"] == []

    # 投影只读：数据库里仍然是 pending / processing，不被列表请求改写。
    async with session_factory() as session:
        overdue = await session.get(AnalysisTask, "task-overdue-pending")
        assert overdue is not None and overdue.status == "pending"
        in_flight = await session.get(AnalysisTask, "task-overdue-processing")
        assert in_flight is not None and in_flight.status == "processing"


# ── 游标分页 ──


@pytest.mark.asyncio
async def test_cursor_paging_covers_every_row_without_duplicates(client, session_factory, users):
    owner = users["owner"]
    expected: list[str] = []
    for index in range(25):
        task_id = f"page-task-{index:02d}"
        expected.append(task_id)  # index 0 is the newest row
        await _seed_task(
            session_factory,
            owner.id,
            task_id,
            created_at=NOW - datetime.timedelta(minutes=index),
        )

    first_page = await _list_tasks(client, owner.id, limit=20)
    assert len(first_page["items"]) == 20
    assert first_page["next_cursor"]

    collected = await _collect_pages(client, owner.id, limit=10)
    ids = [item["task_id"] for item in collected]
    assert ids == expected
    assert len(set(ids)) == len(ids) == 25


@pytest.mark.asyncio
async def test_cursor_paging_is_stable_for_rows_sharing_the_same_timestamp(
    client, session_factory, users
):
    """同一秒内创建的任务也只能靠 (created_at, task_id) 排序，翻页不得重复或丢失。"""
    owner = users["owner"]
    shared = NOW - datetime.timedelta(minutes=1)
    tied = [f"tie-{index:02d}" for index in range(12)]
    for task_id in tied:
        await _seed_task(session_factory, owner.id, task_id, created_at=shared)
    for index in range(5):
        await _seed_task(
            session_factory,
            owner.id,
            f"older-{index}",
            created_at=shared - datetime.timedelta(minutes=index + 1),
        )

    collected = await _collect_pages(client, owner.id, limit=5)
    ids = [item["task_id"] for item in collected]
    assert len(ids) == 17
    assert len(set(ids)) == 17
    # 同一时间戳内按 task_id 倒序，再按 created_at 倒序。
    assert ids[:12] == sorted(tied, reverse=True)
    assert ids[12:] == [f"older-{index}" for index in range(5)]


@pytest.mark.asyncio
async def test_default_limit_is_twenty(client, session_factory, users):
    owner = users["owner"]
    for index in range(21):
        await _seed_task(
            session_factory,
            owner.id,
            f"default-limit-{index:02d}",
            created_at=NOW - datetime.timedelta(minutes=index),
        )

    body = await _list_tasks(client, owner.id)

    assert len(body["items"]) == 20
    assert body["next_cursor"]


# ── 非法参数 ──


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [
        "not-a-cursor",
        "!!!not base64!!!",
        "",
        _encode_cursor([]),
        _encode_cursor({"created_at": "2026-01-01T00:00:00+00:00"}),
        _encode_cursor({"task_id": "abc"}),
        _encode_cursor({"created_at": "2026-01-01T00:00:00", "task_id": "abc"}),
        _encode_cursor({"created_at": 123, "task_id": "abc"}),
        _encode_cursor({"created_at": "2026-01-01T00:00:00+00:00", "task_id": ""}),
        _encode_cursor(
            {"created_at": "2026-01-01T00:00:00+00:00", "task_id": "abc", "extra": "no"}
        ),
    ],
)
async def test_invalid_cursor_returns_422_with_stable_code(client, users, cursor):
    response = await client.get(
        "/api/vision/tasks",
        params={"cursor": cursor},
        headers=auth_headers(users["owner"].id),
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "invalid_cursor"


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"limit": -1}])
async def test_out_of_range_limit_is_rejected(client, users, params):
    response = await client.get(
        "/api/vision/tasks",
        params=params,
        headers=auth_headers(users["owner"].id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_status_is_rejected(client, users):
    response = await client.get(
        "/api/vision/tasks",
        params={"status": "queued"},
        headers=auth_headers(users["owner"].id),
    )

    assert response.status_code == 422


# ── 归属隔离 ──


@pytest.mark.asyncio
async def test_task_list_only_returns_the_callers_tasks(client, session_factory, users):
    owner = users["owner"]
    stranger = users["stranger"]
    await _seed_task(session_factory, owner.id, "owner-task-1")
    await _seed_task(session_factory, owner.id, "owner-task-2")
    await _seed_task(session_factory, stranger.id, "stranger-task-1")

    stranger_list = await _list_tasks(client, stranger.id)
    assert [item["task_id"] for item in stranger_list["items"]] == ["stranger-task-1"]

    # 没有 id 参数可探测；多余的查询参数不改变归属语义。
    probed = await _list_tasks(client, stranger.id, user_id=owner.id, task_id="owner-task-1")
    assert [item["task_id"] for item in probed["items"]] == ["stranger-task-1"]
    assert "owner-task" not in json.dumps(probed)


# ── 历史与任务对齐 ──


@pytest.mark.asyncio
async def test_history_returns_task_id_and_excludes_failed_or_expired_analyses(
    client, session_factory, users
):
    owner = users["owner"]
    completed_record_id = await _seed_record(
        session_factory, owner.id, created_at=NOW - datetime.timedelta(minutes=1)
    )
    legacy_record_id = await _seed_record(
        session_factory, owner.id, created_at=NOW - datetime.timedelta(minutes=2)
    )
    orphaned_record_id = await _seed_record(
        session_factory, owner.id, created_at=NOW - datetime.timedelta(minutes=3)
    )

    await _seed_task(
        session_factory,
        owner.id,
        "history-completed-task",
        status="completed",
        stage="done",
        attempt=1,
        progress=100,
        history_record_id=completed_record_id,
        created_at=NOW - datetime.timedelta(minutes=1),
    )
    await _seed_task(
        session_factory,
        owner.id,
        "history-failed-task",
        status="failed",
        stage="done",
        error_code="provider_timeout",
        created_at=NOW - datetime.timedelta(minutes=4),
    )
    await _seed_task(
        session_factory,
        owner.id,
        "history-expired-task",
        status="expired",
        stage="done",
        error_code="task_expired",
        expires_at=NOW - datetime.timedelta(minutes=1),
        created_at=NOW - datetime.timedelta(minutes=5),
    )
    # 防御性场景：历史行被一条非 completed 的任务引用，不应出现在历史列表。
    await _seed_task(
        session_factory,
        owner.id,
        "history-orphaned-task",
        status="failed",
        stage="done",
        error_code="internal_error",
        history_record_id=orphaned_record_id,
        created_at=NOW - datetime.timedelta(minutes=6),
    )

    response = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=auth_headers(owner.id),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    by_id = {item["id"]: item for item in body["records"]}
    assert set(by_id) == {completed_record_id, legacy_record_id}
    assert body["total"] == 2
    assert by_id[completed_record_id]["task_id"] == "history-completed-task"
    # 旧数据（没有关联任务）保持可读，只是拿不到任务标识。
    assert by_id[legacy_record_id]["task_id"] is None

    # 既有字段保持向后兼容（新增 task_id 不改变旧前端解析）。
    for item in body["records"]:
        assert HISTORY_FIELDS <= set(item)
        assert item["image_thumbnail"] is None
        assert item["image_url"] is None
        assert item["thumbnail_url"] is None
        assert item["degraded"] is False
        assert item["result"]["body_type"] == "mesomorph"

    # 失败与过期任务只出现在任务列表，不出现在历史列表。
    tasks = await _list_tasks(client, owner.id)
    task_ids = {item["task_id"] for item in tasks["items"]}
    assert {"history-completed-task", "history-failed-task", "history-expired-task"} <= task_ids
    completed_task = next(
        item for item in tasks["items"] if item["task_id"] == "history-completed-task"
    )
    assert completed_task["history_record_id"] == completed_record_id
