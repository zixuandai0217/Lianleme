"""资产清理与孤儿巡检契约（工单 16）。

覆盖：删除分析记录 → 对象消失、旧签名链接与重新签发的链接都不可用；用户级清空
的计数、幂等与用户隔离；孤儿巡检的宽限期与批次数；反向巡检的降级与事件；管理员
专属入口。存储端口替换为内存实现（可推进时钟），不依赖 MinIO。
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.logging import (
    EVENT_MEDIA_ASSET_DEGRADED,
    EVENT_MEDIA_CLEANUP_COMPLETED,
    FIELD_ASSET_ID,
    FIELD_BATCHES,
    FIELD_DELETED_ASSETS,
    FIELD_DELETED_OBJECTS,
    FIELD_KIND,
    FIELD_SCANNED,
    FIELD_SCOPE,
    FIELD_SKIPPED_YOUNG,
    StructuredJsonFormatter,
)
from app.core.storage import InMemoryStorage, StorageError, get_storage
from app.main import app
from app.models.body_analysis import BodyAnalysisRecord
from app.models.media_asset import MediaAsset
from app.models.user import User
from app.schemas.vision import BodyAnalysisResult
from app.services.media.cleanup_service import (
    SCOPE_ORPHAN,
    SCOPE_RECORD,
    SCOPE_USER,
    user_prefix,
)
from app.services.media.media_asset_service import (
    ERROR_CODE_ASSET_NOT_FOUND,
    build_object_key,
    build_thumbnail_key,
    generate_asset_id,
)


def _png_bytes(rgb: tuple[int, int, int] = (20, 40, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _analysis_result() -> dict:
    return BodyAnalysisResult(
        body_type="mesomorph",
        body_fat_range="15-20%",
        weak_muscles=["背"],
        strengths=["腿"],
        muscle_scores={"back": 6},
        summary="保持训练",
    ).model_dump()


def _events(caplog, event: str) -> list[dict]:
    formatter = StructuredJsonFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if getattr(record, "fields", {}).get("event") == event
    ]


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'media-cleanup.db').as_posix()}",
        future=True,
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="cleanup-owner", nickname="Owner")
        stranger = User(openid="cleanup-stranger", nickname="Stranger")
        admin = User(openid="cleanup-admin", nickname="Admin", is_admin=True)
        session.add_all([owner, stranger, admin])
        await session.commit()
        for user in (owner, stranger, admin):
            await session.refresh(user)
        return {"owner": owner, "stranger": stranger, "admin": admin}


@pytest.fixture
def storage() -> InMemoryStorage:
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


@pytest.fixture(autouse=True)
def cleanup_settings(monkeypatch):
    """每个用例从确定的配置出发：批次大小与宽限期都在用例里显式覆盖。"""
    monkeypatch.setattr(settings, "MEDIA_CLEANUP_BATCH_SIZE", 50)
    monkeypatch.setattr(settings, "MEDIA_ORPHAN_GRACE_SECONDS", 86_400)


async def _upload(client: AsyncClient, user_id: int, data: bytes) -> str:
    response = await client.post(
        "/api/media/assets",
        files={"file": ("body.png", data, "image/png")},
        headers=_auth(user_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["asset_id"]


async def _seed_asset(
    session_factory,
    storage: InMemoryStorage,
    user_id: int,
    *,
    kind: str = "original",
    object_key: str | None = None,
    data: bytes | None = None,
    status: str = "available",
    write_object: bool = True,
) -> MediaAsset:
    """登记一行资产；``write_object=False`` 用于「记录在但对象丢」的反向巡检。"""
    payload = data if data is not None else _png_bytes()
    asset_id = generate_asset_id()
    key = object_key or build_object_key(user_id, asset_id, "image/png")
    if write_object:
        await storage.write(key, payload, "image/png")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            width, height = image.size
    except Exception:
        width, height = None, None
    async with session_factory() as session:
        asset = MediaAsset(
            asset_id=asset_id,
            user_id=user_id,
            kind=kind,
            object_key=key,
            content_type="image/png",
            size_bytes=len(payload),
            width=width,
            height=height,
            checksum=hashlib.sha256(payload).hexdigest(),
            status=status,
        )
        session.add(asset)
        await session.commit()
    return asset


async def _seed_record(
    session_factory,
    user_id: int,
    *,
    image_asset_id: str | None = None,
    thumbnail_asset_id: str | None = None,
) -> int:
    async with session_factory() as session:
        record = BodyAnalysisRecord(
            user_id=user_id,
            image_asset_id=image_asset_id,
            thumbnail_asset_id=thumbnail_asset_id,
            result=_analysis_result(),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def _asset(session_factory, asset_id: str) -> MediaAsset | None:
    async with session_factory() as session:
        return await session.get(MediaAsset, asset_id)


async def _record_exists(session_factory, record_id: int) -> bool:
    async with session_factory() as session:
        return await session.get(BodyAnalysisRecord, record_id) is not None


# ── 存储端口枚举（维护路径唯一新增操作） ──


@pytest.mark.asyncio
async def test_in_memory_storage_lists_objects_with_age_and_prefix(storage):
    """枚举给出对象年龄，前缀过滤保证用户级清理不会看到别人的对象。"""
    await storage.write("dev/1/202611/as_old.png", b"old", "image/png")
    storage.advance(30)
    await storage.write("dev/1/202612/as_new.png", b"new", "image/png")

    listed = {obj.key: obj.age_seconds for obj in await storage.list_objects("dev/1/")}

    assert set(listed) == {"dev/1/202611/as_old.png", "dev/1/202612/as_new.png"}
    assert listed["dev/1/202611/as_old.png"] == pytest.approx(30, abs=0.5)
    assert listed["dev/1/202612/as_new.png"] == pytest.approx(0, abs=0.5)
    assert await storage.list_objects("dev/2/") == []

    storage.advance(120)
    aged = {obj.key: obj.age_seconds for obj in await storage.list_objects("dev/1/")}
    assert aged["dev/1/202611/as_old.png"] == pytest.approx(150, abs=0.5)


# ── 删除分析记录 ──


@pytest.mark.asyncio
async def test_delete_record_removes_objects_and_invalidates_links(
    client, session_factory, storage, users, caplog
):
    caplog.set_level(logging.INFO)
    owner = users["owner"]
    original = await _seed_asset(session_factory, storage, owner.id)
    thumbnail = await _seed_asset(
        session_factory,
        storage,
        owner.id,
        kind="thumbnail",
        object_key=build_thumbnail_key(original.object_key),
    )
    record_id = await _seed_record(
        session_factory,
        owner.id,
        image_asset_id=original.asset_id,
        thumbnail_asset_id=thumbnail.asset_id,
    )
    signed = await client.get(
        f"/api/media/assets/{original.asset_id}/url", headers=_auth(owner.id)
    )
    old_url = signed.json()["url"]
    assert await storage.fetch(old_url) == await storage.read(original.object_key)

    response = await client.delete(
        f"/api/vision/record/{record_id}", headers=_auth(owner.id)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted_objects": 2, "deleted_assets": 2, "batches": 1}
    assert await _record_exists(session_factory, record_id) is False
    assert storage.object_count == 0
    # 之前拿到的签名链接立刻失效：对象已经不在了。
    with pytest.raises(StorageError):
        await storage.fetch(old_url)

    for asset_id in (original.asset_id, thumbnail.asset_id):
        asset = await _asset(session_factory, asset_id)
        assert asset is not None
        assert asset.status == "deleted"
        assert asset.deleted_at is not None

    # 重新换取链接也只能得到统一的 404，而不是 5xx。
    again = await client.get(
        f"/api/media/assets/{original.asset_id}/url", headers=_auth(owner.id)
    )
    assert again.status_code == 404
    assert again.json()["detail"]["code"] == ERROR_CODE_ASSET_NOT_FOUND

    cleanup_events = _events(caplog, EVENT_MEDIA_CLEANUP_COMPLETED)
    assert cleanup_events, "删除记录必须留下清理计数事件"
    assert cleanup_events[-1][FIELD_SCOPE] == SCOPE_RECORD
    assert cleanup_events[-1][FIELD_DELETED_OBJECTS] == 2
    assert cleanup_events[-1][FIELD_DELETED_ASSETS] == 2


@pytest.mark.asyncio
async def test_failed_object_delete_is_retried_by_the_sweep_queue(
    client, session_factory, storage, users, monkeypatch
):
    """对象删除失败 → 资产留在待清理队列；巡检重试成功后才标记已删除。"""
    owner = users["owner"]
    asset = await _seed_asset(session_factory, storage, owner.id)
    record_id = await _seed_record(
        session_factory, owner.id, image_asset_id=asset.asset_id
    )

    original_delete = storage.delete

    async def failing_delete(key: str) -> None:
        raise StorageError("storage down")

    monkeypatch.setattr(storage, "delete", failing_delete)
    response = await client.delete(
        f"/api/vision/record/{record_id}", headers=_auth(owner.id)
    )
    assert response.status_code == 200, response.text
    queued = await _asset(session_factory, asset.asset_id)
    assert queued is not None
    assert queued.status == "pending_delete"
    assert storage.object_count == 1
    # 待清理期间旧签名链接仍然可用（对象还在）——这正是必须最终删掉它的原因。
    assert await storage.fetch((await storage.sign(asset.object_key, 60))[0])

    monkeypatch.setattr(storage, "delete", original_delete)
    sweep = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["admin"].id)
    )
    assert sweep.status_code == 200, sweep.text
    body = sweep.json()
    assert body["deleted_orphans"] >= 1

    healed = await _asset(session_factory, asset.asset_id)
    assert healed is not None
    assert healed.status == "deleted"
    assert storage.object_count == 0
    resigned = await client.get(
        f"/api/media/assets/{asset.asset_id}/url", headers=_auth(owner.id)
    )
    assert resigned.status_code == 404


@pytest.mark.asyncio
async def test_delete_record_is_owner_only_and_missing_is_404(
    client, session_factory, storage, users
):
    owner = users["owner"]
    stranger = users["stranger"]
    asset = await _seed_asset(session_factory, storage, owner.id)
    record_id = await _seed_record(session_factory, owner.id, image_asset_id=asset.asset_id)

    forbidden = await client.delete(
        f"/api/vision/record/{record_id}", headers=_auth(stranger.id)
    )
    missing = await client.delete(
        "/api/vision/record/999999", headers=_auth(stranger.id)
    )
    unauthenticated = await client.delete(f"/api/vision/record/{record_id}")

    assert forbidden.status_code == 403
    assert missing.status_code == 404
    assert unauthenticated.status_code == 401
    # 越权请求不能改动任何状态：记录还在、对象还在、资产仍可用。
    assert await _record_exists(session_factory, record_id) is True
    assert storage.object_count == 1
    assert (await _asset(session_factory, asset.asset_id)).status == "available"


@pytest.mark.asyncio
async def test_delete_record_without_assets_only_removes_row(
    client, session_factory, storage, users
):
    record_id = await _seed_record(session_factory, users["owner"].id)

    response = await client.delete(
        f"/api/vision/record/{record_id}", headers=_auth(users["owner"].id)
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_objects": 0, "deleted_assets": 0, "batches": 0}
    assert await _record_exists(session_factory, record_id) is False
    assert storage.object_count == 0


@pytest.mark.asyncio
async def test_delete_record_keeps_asset_still_referenced_by_another_record(
    client, session_factory, storage, users
):
    owner = users["owner"]
    asset = await _seed_asset(session_factory, storage, owner.id)
    first = await _seed_record(session_factory, owner.id, image_asset_id=asset.asset_id)
    second = await _seed_record(session_factory, owner.id, image_asset_id=asset.asset_id)

    first_delete = await client.delete(
        f"/api/vision/record/{first}", headers=_auth(owner.id)
    )

    assert first_delete.status_code == 200
    assert first_delete.json() == {
        "deleted_objects": 0,
        "deleted_assets": 0,
        "batches": 0,
    }
    assert storage.object_count == 1
    assert (await _asset(session_factory, asset.asset_id)).status == "available"

    second_delete = await client.delete(
        f"/api/vision/record/{second}", headers=_auth(owner.id)
    )

    assert second_delete.status_code == 200
    assert second_delete.json()["deleted_objects"] == 1
    assert storage.object_count == 0
    assert (await _asset(session_factory, asset.asset_id)).status == "deleted"


# ── 用户级清空 ──


@pytest.mark.asyncio
async def test_user_purge_counts_is_idempotent_and_isolated(
    client, session_factory, storage, users, caplog
):
    caplog.set_level(logging.INFO)
    owner = users["owner"]
    stranger = users["stranger"]
    owner_assets = [
        await _upload(client, owner.id, _png_bytes((1, 2, 3))),
        await _upload(client, owner.id, _png_bytes((4, 5, 6))),
    ]
    stranger_asset = await _upload(client, stranger.id, _png_bytes((7, 8, 9)))

    signed = await client.get(
        f"/api/media/assets/{owner_assets[0]}/url", headers=_auth(owner.id)
    )
    old_url = signed.json()["url"]

    response = await client.delete(
        f"/api/media/users/{owner.id}/assets", headers=_auth(owner.id)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted_objects": 2, "deleted_assets": 2, "batches": 1}
    with pytest.raises(StorageError):
        await storage.fetch(old_url)

    for asset_id in owner_assets:
        asset = await _asset(session_factory, asset_id)
        assert asset is not None
        assert asset.status == "deleted"
    stranger_row = await _asset(session_factory, stranger_asset)
    assert stranger_row is not None
    assert stranger_row.status == "available"
    assert await storage.exists(stranger_row.object_key) is True
    # 只触碰本人前缀：其他用户的对象既未被列举也未被删除。
    assert len(await storage.list_objects(user_prefix(stranger.id))) == 1

    # 重复执行不报错，返回全零。
    repeat = await client.delete(
        f"/api/media/users/{owner.id}/assets", headers=_auth(owner.id)
    )
    assert repeat.status_code == 200
    assert repeat.json() == {"deleted_objects": 0, "deleted_assets": 0, "batches": 0}

    cleanup_events = _events(caplog, EVENT_MEDIA_CLEANUP_COMPLETED)
    assert cleanup_events
    assert cleanup_events[-1][FIELD_SCOPE] == SCOPE_USER
    assert cleanup_events[-1][FIELD_DELETED_OBJECTS] == 2


@pytest.mark.asyncio
async def test_user_purge_respects_batch_size_and_logs_batches(
    client, session_factory, storage, users, caplog, monkeypatch
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "MEDIA_CLEANUP_BATCH_SIZE", 2)
    owner = users["owner"]
    for index in range(3):
        await _upload(client, owner.id, _png_bytes((index, index, index)))

    response = await client.delete(
        f"/api/media/users/{owner.id}/assets", headers=_auth(owner.id)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted_objects": 3, "deleted_assets": 3, "batches": 2}
    assert storage.object_count == 0
    cleanup_events = _events(caplog, EVENT_MEDIA_CLEANUP_COMPLETED)
    assert cleanup_events[-1][FIELD_BATCHES] == 2
    assert cleanup_events[-1][FIELD_DELETED_OBJECTS] == 3


@pytest.mark.asyncio
async def test_user_purge_forbids_other_users(client, session_factory, storage, users):
    owner = users["owner"]
    stranger = users["stranger"]
    await _upload(client, owner.id, _png_bytes((1, 1, 1)))

    response = await client.delete(
        f"/api/media/users/{owner.id}/assets", headers=_auth(stranger.id)
    )

    assert response.status_code == 403
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(MediaAsset))
    assert count == 1
    assert storage.object_count == 1


# ── 孤儿巡检 ──


@pytest.mark.asyncio
async def test_orphan_sweep_deletes_old_orphans_and_keeps_young(
    client, session_factory, storage, users, caplog, monkeypatch
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "MEDIA_ORPHAN_GRACE_SECONDS", 100)
    owner = users["owner"]
    referenced = await _seed_asset(session_factory, storage, owner.id)
    old_orphan = f"{settings.APP_ENV}/{owner.id}/202601/as_old_orphan.png"
    await storage.write(old_orphan, b"old", "image/png")
    # 先写「老」对象，再推进时钟，最后写「年轻」对象：同一存储里出现两种年龄。
    storage.advance(10_000)
    young_orphan = f"{settings.APP_ENV}/{owner.id}/202611/as_young_orphan.png"
    await storage.write(young_orphan, b"young", "image/png")

    response = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["admin"].id)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "scanned": 2,
        "deleted_orphans": 1,
        "degraded_assets": 0,
        "batches": 1,
        "skipped_young": 1,
    }
    assert await storage.exists(old_orphan) is False
    assert await storage.exists(young_orphan) is True
    # 被资产行引用的对象即使年龄很大也不是孤儿。
    assert await storage.exists(referenced.object_key) is True
    assert (await _asset(session_factory, referenced.asset_id)).status == "available"

    cleanup_events = _events(caplog, EVENT_MEDIA_CLEANUP_COMPLETED)
    assert cleanup_events
    assert cleanup_events[-1][FIELD_SCOPE] == SCOPE_ORPHAN
    assert cleanup_events[-1][FIELD_SCANNED] == 2
    assert cleanup_events[-1][FIELD_SKIPPED_YOUNG] == 1
    assert cleanup_events[-1][FIELD_DELETED_OBJECTS] == 1


@pytest.mark.asyncio
async def test_orphan_sweep_is_batched_and_reentrant(
    client, session_factory, storage, users, caplog, monkeypatch
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "MEDIA_CLEANUP_BATCH_SIZE", 2)
    monkeypatch.setattr(settings, "MEDIA_ORPHAN_GRACE_SECONDS", 100)
    owner = users["owner"]
    for index in range(4):
        await storage.write(
            f"{settings.APP_ENV}/{owner.id}/202601/as_orphan_{index}.png",
            b"orphan",
            "image/png",
        )
    storage.advance(1_000)

    first = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["admin"].id)
    )
    second = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["admin"].id)
    )
    third = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["admin"].id)
    )

    assert first.json() == {
        "scanned": 2,
        "deleted_orphans": 2,
        "degraded_assets": 0,
        "batches": 1,
        "skipped_young": 0,
    }
    assert second.json() == first.json()
    assert third.json() == {
        "scanned": 0,
        "deleted_orphans": 0,
        "degraded_assets": 0,
        "batches": 0,
        "skipped_young": 0,
    }
    assert storage.object_count == 0
    # 只有真正做了工作的两次巡检留下计数事件。
    assert len(_events(caplog, EVENT_MEDIA_CLEANUP_COMPLETED)) == 2


@pytest.mark.asyncio
async def test_reverse_sweep_degrades_missing_asset_and_logs_event(
    client, session_factory, storage, users, caplog
):
    caplog.set_level(logging.INFO)
    owner = users["owner"]
    asset = await _seed_asset(session_factory, storage, owner.id, write_object=False)

    response = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["admin"].id)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded_assets"] == 1
    assert body["deleted_orphans"] == 0
    assert body["batches"] >= 1

    row = await _asset(session_factory, asset.asset_id)
    assert row is not None
    assert row.status == "degraded"

    degraded_events = _events(caplog, EVENT_MEDIA_ASSET_DEGRADED)
    assert degraded_events, "反向巡检必须留下降级事件"
    event = degraded_events[-1]
    assert event[FIELD_ASSET_ID] == asset.asset_id
    assert event[FIELD_KIND] == "original"
    assert event["user_id"] == owner.id

    # 降级后的签名读图是统一 404 语义，不是 5xx。
    sign = await client.get(
        f"/api/media/assets/{asset.asset_id}/url", headers=_auth(owner.id)
    )
    assert sign.status_code == 404
    assert sign.json()["detail"]["code"] == ERROR_CODE_ASSET_NOT_FOUND
    assert sign.status_code < 500


@pytest.mark.asyncio
async def test_sweep_requires_admin(client, storage, users):
    normal = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["owner"].id)
    )
    anonymous = await client.post("/api/media/maintenance/sweep")
    admin = await client.post(
        "/api/media/maintenance/sweep", headers=_auth(users["admin"].id)
    )

    assert normal.status_code == 403
    assert anonymous.status_code == 401
    assert admin.status_code == 200
