"""媒体资产路由契约：上传、去重、签名读图与分析资产引用（工单 14）。

只断言外部可观察行为：HTTP 状态、稳定错误码、响应字段、数据库里只留 key 与元数据、
对象存储中对象数量与内容。存储端口替换为内存实现，不依赖 MinIO。
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import io
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import vision as vision_api
from app.api.media_errors import ERROR_CODE_CHECKSUM_MISMATCH
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.logging import (
    EVENT_MEDIA_THUMBNAIL_FAILED,
    EVENT_MEDIA_UPLOAD_REJECTED,
    StructuredJsonFormatter,
)
from app.core.storage import InMemoryStorage, StorageError, get_storage
from app.main import app
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
from app.models.media_asset import MediaAsset
from app.models.user import User
from app.schemas.vision import AnalyzeRequest, BodyAnalysisResult
from app.services.media.media_asset_service import (
    ERROR_CODE_ASSET_NOT_FOUND,
    ERROR_CODE_IMAGE_ANIMATED,
    ERROR_CODE_IMAGE_TOO_SMALL,
    ERROR_CODE_IMAGE_TYPE_MISMATCH,
    ERROR_CODE_PAYLOAD_TOO_LARGE,
    ERROR_CODE_UNSUPPORTED_MEDIA_TYPE,
    build_object_key,
    generate_asset_id,
)
from app.services.user.api_key_service import ApiKeyService

NOW = datetime.datetime.now(datetime.timezone.utc)


def _png_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (20, 40, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes(width: int = 800, height: int = 600) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (30, 60, 90)).save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _webp_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (30, 90, 60)).save(buffer, format="WEBP", quality=95)
    return buffer.getvalue()


def _exif_oriented_jpeg(width: int = 800, height: int = 600) -> bytes:
    """带 EXIF 方向 6 与 GPS 的 JPEG；左上角红色块用于断言像素确实被旋转。"""
    image = Image.new("RGB", (width, height), (20, 40, 60))
    for y in range(40):
        for x in range(40):
            image.putpixel((x, y), (255, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x8825] = {1: "N", 2: (31.0, 13.0, 0.0), 3: "E", 4: (121.0, 28.0, 0.0)}
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95, exif=exif)
    return buffer.getvalue()


def _animated_png_bytes(width: int = 640, height: int = 480) -> bytes:
    frames = [
        Image.new("RGBA", (width, height), (255, 0, 0, 255)),
        Image.new("RGBA", (width, height), (0, 255, 0, 255)),
    ]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="PNG", save_all=True, append_images=frames[1:])
    return buffer.getvalue()


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'media-assets.db').as_posix()}",
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
        owner = User(openid="media-owner", nickname="Owner")
        stranger = User(openid="media-stranger", nickname="Stranger")
        session.add_all([owner, stranger])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(stranger)
        await ApiKeyService(session).save_key(owner.id, "openai", "sk-owner-media-123456")
        await ApiKeyService(session).save_key(stranger.id, "openai", "sk-stranger-media-123")
        await session.commit()
        return {"owner": owner, "stranger": stranger}


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
def stub_background(monkeypatch):
    """HTTP 测试不真正执行后台分析；仍保留原始入口供断言调用。"""
    original = vision_api._run_analysis
    stub = AsyncMock()
    monkeypatch.setattr(vision_api, "_run_analysis", stub)
    return {"original": original, "stub": stub}


async def _asset_count(session_factory) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(MediaAsset)) or 0)


async def _task_count(session_factory) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(AnalysisTask)) or 0)


async def _upload(
    client: AsyncClient,
    user_id: int,
    data: bytes,
    *,
    filename: str = "body.png",
    content_type: str = "image/png",
    checksum: str | None = None,
):
    form = {"checksum": checksum} if checksum is not None else None
    return await client.post(
        "/api/media/assets",
        files={"file": (filename, data, content_type)},
        data=form,
        headers=_auth(user_id),
    )


async def _seed_asset(
    session_factory,
    storage: InMemoryStorage,
    user_id: int,
    data: bytes | None = None,
    *,
    content_type: str = "image/png",
) -> MediaAsset:
    payload = data if data is not None else _png_bytes()
    asset_id = generate_asset_id()
    key = build_object_key(user_id, asset_id, content_type)
    await storage.write(key, payload, content_type)
    try:
        with Image.open(io.BytesIO(payload)) as image:
            width, height = image.size
    except Exception:
        # 损坏内容也要能落成既有资产，供缩略图降级路径使用。
        width, height = None, None
    async with session_factory() as session:
        asset = MediaAsset(
            asset_id=asset_id,
            user_id=user_id,
            kind="original",
            object_key=key,
            content_type=content_type,
            size_bytes=len(payload),
            width=width,
            height=height,
            checksum=hashlib.sha256(payload).hexdigest(),
            status="available",
        )
        session.add(asset)
        await session.commit()
    return asset


async def _seed_task(
    session_factory,
    user_id: int,
    task_id: str,
    image_asset_id: str,
) -> None:
    async with session_factory() as session:
        session.add(
            AnalysisTask(
                task_id=task_id,
                user_id=user_id,
                status="pending",
                stage="queued",
                attempt=0,
                progress=0,
                image_asset_id=image_asset_id,
                expires_at=NOW + datetime.timedelta(minutes=10),
            )
        )
        await session.commit()


class _SuccessfulVisionGraph:
    """后台执行器的替身：返回固定分析结果，不调用模型。"""

    def __init__(self, user_id: int, db) -> None:
        self.user_id = user_id
        self.db = db

    async def run(self, image_base64: str, profile=None) -> BodyAnalysisResult:
        return BodyAnalysisResult(**_analysis_result())


def _analysis_result() -> dict:
    return BodyAnalysisResult(
        body_type="mesomorph",
        body_fat_range="15-20%",
        weak_muscles=["背"],
        strengths=["腿"],
        muscle_scores={"back": 6},
        summary="保持训练",
    ).model_dump()


async def _execute_analysis(
    monkeypatch,
    session_factory,
    stub_background,
    storage: InMemoryStorage,
    *,
    task_id: str,
    user_id: int,
    image_asset_id: str,
) -> None:
    """直接运行真实后台执行器，只替换模型与数据库工厂。"""
    monkeypatch.setattr(vision_api, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(vision_api, "VisionGraph", _SuccessfulVisionGraph)
    await stub_background["original"](
        task_id,
        AnalyzeRequest(user_id=user_id, image_asset_id=image_asset_id),
        storage,
    )


def _events(caplog, event: str) -> list[dict]:
    formatter = StructuredJsonFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if getattr(record, "fields", {}).get("event") == event
    ]


# ── 存储端口单元语义 ──


def test_object_key_is_stable_and_scoped_by_environment_user_and_month():
    moment = datetime.datetime(2026, 11, 2, tzinfo=datetime.timezone.utc)

    first = build_object_key(7, "as_abc", "image/jpeg", moment)
    second = build_object_key(7, "as_abc", "image/jpeg", moment)

    assert first == second
    assert first.startswith(f"{settings.APP_ENV}/7/202611/")
    assert first.endswith(".jpg")
    assert "body.png" not in first


@pytest.mark.asyncio
async def test_in_memory_storage_signed_url_expires(storage: InMemoryStorage):
    """签名 URL 在有效期内可读，过期后不可再用（内存时钟推进，不等待真实时间）。"""
    await storage.write("dev/1/202611/as_x.png", b"payload", "image/png")

    url, expires_at = await storage.sign("dev/1/202611/as_x.png", ttl_seconds=5)

    assert url.startswith("memory://media/")
    assert expires_at > datetime.datetime.now(datetime.timezone.utc)
    assert await storage.fetch(url) == b"payload"

    storage.advance(6)
    with pytest.raises(StorageError):
        await storage.fetch(url)


@pytest.mark.asyncio
async def test_in_memory_storage_read_exists_delete(storage: InMemoryStorage):
    await storage.write("dev/1/202611/as_x.png", b"payload", "image/png")
    assert await storage.exists("dev/1/202611/as_x.png") is True
    assert await storage.read("dev/1/202611/as_x.png") == b"payload"

    url, _ = await storage.sign("dev/1/202611/as_x.png", 60)
    await storage.delete("dev/1/202611/as_x.png")

    assert await storage.exists("dev/1/202611/as_x.png") is False
    with pytest.raises(StorageError):
        await storage.fetch(url)


# ── 上传 ──


@pytest.mark.asyncio
async def test_upload_returns_metadata_and_stores_only_key(
    client, session_factory, storage, users
):
    owner = users["owner"]
    data = _png_bytes()

    response = await _upload(client, owner.id, data, filename="private-name.png")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["asset_id"].startswith("as_")
    assert body["content_type"] == "image/png"
    assert body["width"] == 640
    assert body["height"] == 480
    assert body["created_at"]
    assert "object_key" not in body
    assert "http" not in response.text

    async with session_factory() as session:
        asset = await session.get(MediaAsset, body["asset_id"])
        assert asset is not None
        assert asset.user_id == owner.id
        assert asset.object_key.startswith(f"{settings.APP_ENV}/{owner.id}/")
        assert asset.object_key.endswith(".png")
        assert "private-name" not in asset.object_key
        assert "http" not in asset.object_key
        assert asset.width == 640
        assert asset.original_filename == "private-name.png"

    stored = await storage.read(asset.object_key)
    # 存档字节是重新编码后的清理版本：摘要与字节数都以存档为准。
    assert body["size_bytes"] == len(stored) == asset.size_bytes
    assert body["checksum"] == hashlib.sha256(stored).hexdigest() == asset.checksum
    assert storage.object_count == 1
    with Image.open(io.BytesIO(stored)) as image:
        assert image.size == (640, 480)
        assert image.format == "PNG"


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_content_type_without_rows(
    client, session_factory, storage, users, caplog
):
    caplog.set_level(logging.WARNING)
    owner = users["owner"]

    for filename, content_type in (
        ("body.gif", "image/gif"),
        ("body.pdf", "application/pdf"),
        ("body.heic", "image/heic"),
    ):
        response = await _upload(
            client, owner.id, _png_bytes(), filename=filename, content_type=content_type
        )
        assert response.status_code == 415, response.text
        assert response.json()["detail"]["code"] == ERROR_CODE_UNSUPPORTED_MEDIA_TYPE

    assert await _asset_count(session_factory) == 0
    assert await _task_count(session_factory) == 0
    assert storage.object_count == 0
    rejected = _events(caplog, EVENT_MEDIA_UPLOAD_REJECTED)
    assert rejected, "校验拒绝必须留下可观测事件"
    assert rejected[-1]["error_code"] == ERROR_CODE_UNSUPPORTED_MEDIA_TYPE


@pytest.mark.asyncio
async def test_upload_rejects_payload_over_byte_cap_before_decoding(
    client, session_factory, storage, users, monkeypatch
):
    owner = users["owner"]
    monkeypatch.setattr(settings, "MEDIA_MAX_UPLOAD_BYTES", 1024)

    # 内容本身不是图片：若先解码会得到 400 image_invalid，413 证明字节上限先于解码。
    response = await _upload(
        client, owner.id, b"x" * 2048, filename="huge.png", content_type="image/png"
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == ERROR_CODE_PAYLOAD_TOO_LARGE
    assert await _asset_count(session_factory) == 0
    assert await _task_count(session_factory) == 0
    assert storage.object_count == 0


@pytest.mark.asyncio
async def test_upload_rejects_animated_image_without_rows(
    client, session_factory, storage, users
):
    owner = users["owner"]

    response = await _upload(
        client, owner.id, _animated_png_bytes(), filename="body.png", content_type="image/png"
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == ERROR_CODE_IMAGE_ANIMATED
    assert await _asset_count(session_factory) == 0
    assert await _task_count(session_factory) == 0
    assert storage.object_count == 0


@pytest.mark.asyncio
async def test_upload_rejects_declared_and_actual_type_mismatch(
    client, session_factory, storage, users
):
    owner = users["owner"]

    response = await _upload(
        client, owner.id, _jpeg_bytes(), filename="body.png", content_type="image/png"
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == ERROR_CODE_IMAGE_TYPE_MISMATCH
    assert await _asset_count(session_factory) == 0
    assert await _task_count(session_factory) == 0
    assert storage.object_count == 0


@pytest.mark.asyncio
async def test_upload_rejects_image_below_minimum_edge(
    client, session_factory, storage, users
):
    owner = users["owner"]

    response = await _upload(
        client, owner.id, _png_bytes(400, 480), filename="small.png", content_type="image/png"
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == ERROR_CODE_IMAGE_TOO_SMALL
    assert await _asset_count(session_factory) == 0
    assert await _task_count(session_factory) == 0
    assert storage.object_count == 0


@pytest.mark.asyncio
async def test_upload_accepts_webp_and_preserves_declared_type(
    client, session_factory, storage, users
):
    owner = users["owner"]

    response = await _upload(
        client, owner.id, _webp_bytes(), filename="body.webp", content_type="image/webp"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content_type"] == "image/webp"
    async with session_factory() as session:
        asset = await session.get(MediaAsset, body["asset_id"])
        assert asset is not None
        assert asset.object_key.endswith(".webp")
    stored = await storage.read(asset.object_key)
    with Image.open(io.BytesIO(stored)) as image:
        assert image.format == "WEBP"
        assert image.size == (640, 480)
    assert storage.object_count == 1


@pytest.mark.asyncio
async def test_upload_strips_exif_rotates_pixels_and_cleans_stored_bytes(
    client, session_factory, storage, users
):
    owner = users["owner"]
    data = _exif_oriented_jpeg()

    response = await _upload(
        client, owner.id, data, filename="body.jpg", content_type="image/jpeg"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # EXIF 方向 6 表示需顺时针旋转 90°：800×600 存档后为 600×800。
    assert body["width"] == 600
    assert body["height"] == 800

    async with session_factory() as session:
        asset = await session.get(MediaAsset, body["asset_id"])
        assert asset is not None
        assert (asset.width, asset.height) == (600, 800)

    stored = await storage.read(asset.object_key)
    assert body["size_bytes"] == len(stored) == asset.size_bytes
    assert body["checksum"] == hashlib.sha256(stored).hexdigest()

    with Image.open(io.BytesIO(stored)) as image:
        assert image.size == (600, 800)
        assert image.format == "JPEG"
        # 全部 EXIF（含方向与 GPS）都必须被清除，而不是只清方向。
        assert dict(image.getexif()) == {}
        assert image.getexif().get_ifd(0x8825) == {}
        # 左上角红色块旋转 90° 顺时针后落在右上角。
        assert image.getpixel((image.width - 1, 0))[0] > 200
    assert b"Exif" not in stored


@pytest.mark.asyncio
async def test_repeated_upload_with_same_digest_reuses_asset(
    client, session_factory, storage, users
):
    owner = users["owner"]
    data = _png_bytes()
    digest = hashlib.sha256(data).hexdigest()

    first = await _upload(client, owner.id, data, checksum=digest)
    second = await _upload(client, owner.id, data, filename="retry.png", checksum=digest)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["asset_id"] == second.json()["asset_id"]
    assert storage.object_count == 1
    assert await _asset_count(session_factory) == 1


@pytest.mark.asyncio
async def test_upload_rejects_undecodable_bytes_without_rows(
    client, session_factory, storage, users
):
    owner = users["owner"]

    response = await _upload(client, owner.id, b"definitely-not-an-image")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "image_invalid"
    assert await _asset_count(session_factory) == 0
    assert storage.object_count == 0


@pytest.mark.asyncio
async def test_upload_checksum_mismatch_is_rejected_before_write(
    client, session_factory, storage, users
):
    owner = users["owner"]

    response = await _upload(
        client,
        owner.id,
        _png_bytes(),
        checksum="0" * 64,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == ERROR_CODE_CHECKSUM_MISMATCH
    assert await _asset_count(session_factory) == 0
    assert storage.object_count == 0


@pytest.mark.asyncio
async def test_upload_storage_failure_returns_503_and_creates_nothing(
    client, session_factory, users
):
    owner = users["owner"]
    previous = app.dependency_overrides[get_storage]

    class _FailingStorage(InMemoryStorage):
        async def write(self, key, data, content_type):
            raise StorageError("down")

    app.dependency_overrides[get_storage] = lambda: _FailingStorage()
    try:
        response = await _upload(client, owner.id, _png_bytes())
    finally:
        app.dependency_overrides[get_storage] = previous

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "storage_unavailable"
    assert await _asset_count(session_factory) == 0


# ── 签名读图 ──


@pytest.mark.asyncio
async def test_owner_gets_short_lived_signed_url(client, session_factory, storage, users):
    owner = users["owner"]
    data = _png_bytes()
    uploaded = await _upload(client, owner.id, data)
    asset_id = uploaded.json()["asset_id"]

    response = await client.get(
        f"/api/media/assets/{asset_id}/url",
        headers=_auth(owner.id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["asset_id"] == asset_id
    assert body["kind"] == "original"
    assert body["url"].startswith("memory://media/")
    assert body["content_type"] == "image/png"
    assert body["width"] == 640
    assert body["height"] == 480
    assert body["expires_at"]

    async with session_factory() as session:
        stored_asset = await session.get(MediaAsset, asset_id)
        assert stored_asset is not None
    stored = await storage.read(stored_asset.object_key)
    assert body["size_bytes"] == len(stored)
    assert await storage.fetch(body["url"]) == stored

    # URL 与过期时间不落库：数据库里只有对象 key 与元数据。
    async with session_factory() as session:
        asset = await session.get(MediaAsset, asset_id)
        assert asset is not None
        stored_values = [asset.object_key, asset.content_type, asset.checksum, asset.status]
        assert all(body["url"] not in value for value in stored_values)


@pytest.mark.asyncio
async def test_missing_foreign_and_deleted_assets_share_same_404(
    client, session_factory, users, storage
):
    owner = users["owner"]
    stranger = users["stranger"]
    asset = await _seed_asset(session_factory, storage, owner.id)

    foreign = await client.get(
        f"/api/media/assets/{asset.asset_id}/url",
        headers=_auth(stranger.id),
    )
    missing = await client.get(
        "/api/media/assets/as_does_not_exist/url",
        headers=_auth(owner.id),
    )

    async with session_factory() as session:
        stored = await session.get(MediaAsset, asset.asset_id)
        assert stored is not None
        stored.status = "deleted"
        stored.deleted_at = NOW
        await session.commit()

    deleted = await client.get(
        f"/api/media/assets/{asset.asset_id}/url",
        headers=_auth(owner.id),
    )

    for response in (foreign, missing, deleted):
        assert response.status_code == 404
        assert response.json() == {
            "detail": {"code": ERROR_CODE_ASSET_NOT_FOUND, "message": "资产不存在或无权访问"}
        }
    assert foreign.json() == missing.json() == deleted.json()


@pytest.mark.asyncio
async def test_unauthenticated_signed_read_is_401(client, session_factory, users, storage):
    asset = await _seed_asset(session_factory, storage, users["owner"].id)

    response = await client.get(f"/api/media/assets/{asset.asset_id}/url")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_signing_failure_returns_503(client, session_factory, users):
    owner = users["owner"]
    asset = await _seed_asset(session_factory, InMemoryStorage(), owner.id)
    previous = app.dependency_overrides[get_storage]

    class _FailingSignStorage(InMemoryStorage):
        async def sign(self, key, ttl_seconds):
            raise StorageError("down")

    app.dependency_overrides[get_storage] = lambda: _FailingSignStorage()
    try:
        response = await client.get(
            f"/api/media/assets/{asset.asset_id}/url",
            headers=_auth(owner.id),
        )
    finally:
        app.dependency_overrides[get_storage] = previous

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "storage_unavailable"


# ── 分析任务创建 ──


@pytest.mark.asyncio
async def test_create_task_from_asset_id_persists_only_reference(
    client, session_factory, users, storage
):
    owner = users["owner"]
    asset = await _seed_asset(session_factory, storage, owner.id)

    response = await client.post(
        "/api/vision/analyze",
        json={"user_id": owner.id, "image_asset_id": asset.asset_id},
        headers=_auth(owner.id),
    )

    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task is not None
        assert task.image_asset_id == asset.asset_id
        assert task.input_image_base64 is None
    assert await _asset_count(session_factory) == 1


@pytest.mark.asyncio
async def test_create_task_with_foreign_asset_is_404(client, session_factory, users, storage):
    owner = users["owner"]
    stranger = users["stranger"]
    asset = await _seed_asset(session_factory, storage, owner.id)

    response = await client.post(
        "/api/vision/analyze",
        json={"user_id": stranger.id, "image_asset_id": asset.asset_id},
        headers=_auth(stranger.id),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == ERROR_CODE_ASSET_NOT_FOUND
    assert await _task_count(session_factory) == 0


@pytest.mark.asyncio
async def test_create_task_from_inline_image_persists_asset_first(
    client, session_factory, users, storage
):
    owner = users["owner"]
    data = _png_bytes()

    response = await client.post(
        "/api/vision/analyze",
        json={"user_id": owner.id, "image_base64": base64.b64encode(data).decode()},
        headers=_auth(owner.id),
    )

    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    digest = hashlib.sha256(data).hexdigest()
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task is not None
        assert task.input_image_base64 is None
        assert task.image_asset_id
        asset = await session.get(MediaAsset, task.image_asset_id)
        assert asset is not None
        assert asset.checksum == digest
        assert asset.content_type == "image/png"
    assert storage.object_count == 1
    assert await _asset_count(session_factory) == 1


@pytest.mark.asyncio
async def test_create_task_requires_exactly_one_image_source(client, users):
    owner = users["owner"]

    neither = await client.post(
        "/api/vision/analyze",
        json={"user_id": owner.id},
        headers=_auth(owner.id),
    )
    both = await client.post(
        "/api/vision/analyze",
        json={
            "user_id": owner.id,
            "image_base64": "aW1hZ2U=",
            "image_asset_id": "as_both",
        },
        headers=_auth(owner.id),
    )

    assert neither.status_code == 422
    assert both.status_code == 422


@pytest.mark.asyncio
async def test_create_task_storage_failure_creates_no_task_or_asset(
    client, session_factory, users
):
    owner = users["owner"]
    previous = app.dependency_overrides[get_storage]

    class _FailingStorage(InMemoryStorage):
        async def write(self, key, data, content_type):
            raise StorageError("down")

    app.dependency_overrides[get_storage] = lambda: _FailingStorage()
    try:
        response = await client.post(
            "/api/vision/analyze",
            json={"user_id": owner.id, "image_base64": "aW1hZ2U="},
            headers=_auth(owner.id),
        )
    finally:
        app.dependency_overrides[get_storage] = previous

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "storage_unavailable"
    assert await _task_count(session_factory) == 0
    assert await _asset_count(session_factory) == 0


# ── 历史 / 详情 ──


@pytest.mark.asyncio
async def test_history_and_detail_return_signed_original_and_empty_legacy_thumbnail(
    client, session_factory, users, storage
):
    owner = users["owner"]
    data = _png_bytes()
    asset = await _seed_asset(session_factory, storage, owner.id, data)
    async with session_factory() as session:
        record = BodyAnalysisRecord(
            user_id=owner.id,
            image_thumbnail="bGVnYWN5LXRodW1ibmFpbA==",
            image_asset_id=asset.asset_id,
            result=_analysis_result(),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        record_id = record.id

    history = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=_auth(owner.id),
    )
    detail = await client.get(
        f"/api/vision/record/{record_id}",
        headers=_auth(owner.id),
    )

    for response in (history, detail):
        assert response.status_code == 200, response.text

    item = history.json()["records"][0]
    for body in (item, detail.json()):
        assert body["image_asset_id"] == asset.asset_id
        assert body["thumbnail_asset_id"] is None
        assert body["image_url"].startswith("memory://media/")
        assert body["thumbnail_url"] is None
        assert body["image_thumbnail"] is None
        assert body["degraded"] is False

    assert await storage.fetch(item["image_url"]) == data


@pytest.mark.asyncio
async def test_legacy_history_record_without_asset_returns_empty_urls(
    client, session_factory, users
):
    owner = users["owner"]
    async with session_factory() as session:
        record = BodyAnalysisRecord(
            user_id=owner.id,
            image_thumbnail="bGVnYWN5LXRodW1ibmFpbA==",
            result=_analysis_result(),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        record_id = record.id

    history = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=_auth(owner.id),
    )
    detail = await client.get(
        f"/api/vision/record/{record_id}",
        headers=_auth(owner.id),
    )

    assert history.status_code == 200
    assert detail.status_code == 200
    for body in (history.json()["records"][0], detail.json()):
        assert body["image_url"] is None
        assert body["thumbnail_url"] is None
        assert body["image_thumbnail"] is None
        assert body["degraded"] is False


@pytest.mark.asyncio
async def test_history_never_signs_another_users_asset(
    client, session_factory, users, storage
):
    """归属过滤在查询里：记录即使引用了他人资产，也拿不到签名链接。"""
    owner = users["owner"]
    stranger = users["stranger"]
    foreign_asset = await _seed_asset(session_factory, storage, stranger.id)
    async with session_factory() as session:
        record = BodyAnalysisRecord(
            user_id=owner.id,
            image_asset_id=foreign_asset.asset_id,
            result=_analysis_result(),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        record_id = record.id

    history = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=_auth(owner.id),
    )
    detail = await client.get(
        f"/api/vision/record/{record_id}",
        headers=_auth(owner.id),
    )

    assert history.status_code == 200
    assert detail.status_code == 200
    for body in (history.json()["records"][0], detail.json()):
        assert body["image_url"] is None
        assert body["degraded"] is True


@pytest.mark.asyncio
async def test_history_signing_failure_degrades_item_without_failing_list(
    client, session_factory, users, storage
):
    owner = users["owner"]
    asset = await _seed_asset(session_factory, storage, owner.id)
    async with session_factory() as session:
        session.add(
            BodyAnalysisRecord(
                user_id=owner.id,
                image_asset_id=asset.asset_id,
                result=_analysis_result(),
            )
        )
        await session.commit()

    previous = app.dependency_overrides[get_storage]

    class _FailingSignStorage(InMemoryStorage):
        async def sign(self, key, ttl_seconds):
            raise StorageError("down")

    app.dependency_overrides[get_storage] = lambda: _FailingSignStorage()
    try:
        response = await client.get(
            f"/api/vision/{owner.id}/history",
            headers=_auth(owner.id),
        )
    finally:
        app.dependency_overrides[get_storage] = previous

    assert response.status_code == 200
    item = response.json()["records"][0]
    assert item["image_url"] is None
    assert item["thumbnail_url"] is None
    assert item["degraded"] is True


# ── 缩略图异步生成 ──


@pytest.mark.asyncio
async def test_analysis_generates_thumbnail_and_history_returns_signed_url(
    client, session_factory, storage, users, stub_background, monkeypatch
):
    owner = users["owner"]
    original = await _seed_asset(session_factory, storage, owner.id, _png_bytes(1600, 1200))
    task_id = "thumbnail-success-1"
    await _seed_task(session_factory, owner.id, task_id, original.asset_id)

    await _execute_analysis(
        monkeypatch,
        session_factory,
        stub_background,
        storage,
        task_id=task_id,
        user_id=owner.id,
        image_asset_id=original.asset_id,
    )

    history = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=_auth(owner.id),
    )
    assert history.status_code == 200, history.text
    item = history.json()["records"][0]
    assert item["thumbnail_url"].startswith("memory://media/")
    assert item["degraded"] is False

    thumbnail_bytes = await storage.fetch(item["thumbnail_url"])
    with Image.open(io.BytesIO(thumbnail_bytes)) as thumbnail:
        assert thumbnail.format == "JPEG"
        assert max(thumbnail.size) == settings.MEDIA_THUMBNAIL_MAX_EDGE_PX
        assert thumbnail.size == (800, 600)

    async with session_factory() as session:
        record = await session.get(BodyAnalysisRecord, item["id"])
        assert record is not None
        thumbnail = await session.get(MediaAsset, record.thumbnail_asset_id)
        assert thumbnail is not None
        assert thumbnail.kind == "thumbnail"
        assert thumbnail.status == "available"
        assert thumbnail.content_type == "image/jpeg"
        assert thumbnail.object_key == f"{original.object_key}.thumb.jpg"
        assert (thumbnail.width, thumbnail.height) == (800, 600)
        assert thumbnail.size_bytes == len(thumbnail_bytes)

    assert storage.object_count == 2


@pytest.mark.asyncio
async def test_thumbnail_long_edge_matches_config_even_for_small_uploads(
    client, session_factory, storage, users, stub_background, monkeypatch
):
    """AC3 要求长边等于配置值：比配置小的图也要放大，而不是保留原边长。"""
    owner = users["owner"]
    original = await _seed_asset(session_factory, storage, owner.id, _png_bytes(640, 480))
    task_id = "thumbnail-upscale-1"
    await _seed_task(session_factory, owner.id, task_id, original.asset_id)

    await _execute_analysis(
        monkeypatch,
        session_factory,
        stub_background,
        storage,
        task_id=task_id,
        user_id=owner.id,
        image_asset_id=original.asset_id,
    )

    history = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=_auth(owner.id),
    )
    assert history.status_code == 200, history.text
    item = history.json()["records"][0]
    assert item["thumbnail_url"].startswith("memory://media/")

    thumbnail_bytes = await storage.fetch(item["thumbnail_url"])
    with Image.open(io.BytesIO(thumbnail_bytes)) as thumbnail:
        assert thumbnail.format == "JPEG"
        assert thumbnail.size == (800, 600)
        assert max(thumbnail.size) == settings.MEDIA_THUMBNAIL_MAX_EDGE_PX


@pytest.mark.asyncio
async def test_thumbnail_generation_is_idempotent_for_the_same_original(
    client, session_factory, storage, users, stub_background, monkeypatch
):
    owner = users["owner"]
    original = await _seed_asset(session_factory, storage, owner.id, _png_bytes(1600, 1200))

    for index in (1, 2):
        task_id = f"thumbnail-idempotent-{index}"
        await _seed_task(session_factory, owner.id, task_id, original.asset_id)
        await _execute_analysis(
            monkeypatch,
            session_factory,
            stub_background,
            storage,
            task_id=task_id,
            user_id=owner.id,
            image_asset_id=original.asset_id,
        )

    # 原图 + 唯一一份缩略图；第二次触发不写出新对象。
    assert storage.object_count == 2
    async with session_factory() as session:
        thumbnails = list(
            (
                await session.execute(
                    select(MediaAsset).where(MediaAsset.kind == "thumbnail")
                )
            )
            .scalars()
            .all()
        )
        assert len(thumbnails) == 1
        records = list(
            (
                await session.execute(
                    select(BodyAnalysisRecord).order_by(BodyAnalysisRecord.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(records) == 2
        assert {record.thumbnail_asset_id for record in records} == {thumbnails[0].asset_id}
        tasks = list(
            (
                await session.execute(
                    select(AnalysisTask).order_by(AnalysisTask.task_id)
                )
            )
            .scalars()
            .all()
        )
        assert {task.thumbnail_asset_id for task in tasks} == {thumbnails[0].asset_id}


@pytest.mark.asyncio
async def test_thumbnail_failure_degrades_history_without_hiding_analysis(
    client, session_factory, storage, users, stub_background, monkeypatch, caplog
):
    caplog.set_level(logging.WARNING)
    owner = users["owner"]
    original = await _seed_asset(session_factory, storage, owner.id, b"not-an-image")
    task_id = "thumbnail-failure-1"
    await _seed_task(session_factory, owner.id, task_id, original.asset_id)

    await _execute_analysis(
        monkeypatch,
        session_factory,
        stub_background,
        storage,
        task_id=task_id,
        user_id=owner.id,
        image_asset_id=original.asset_id,
    )

    history = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=_auth(owner.id),
    )
    assert history.status_code == 200, history.text
    item = history.json()["records"][0]
    # 分析结果仍然可读，原图链接照常签发。
    assert item["result"]["body_type"] == "mesomorph"
    assert item["image_url"].startswith("memory://media/")
    assert await storage.fetch(item["image_url"]) == b"not-an-image"
    assert item["thumbnail_url"] is None
    assert item["degraded"] is True
    assert item["thumbnail_asset_id"] is not None

    async with session_factory() as session:
        record = await session.get(BodyAnalysisRecord, item["id"])
        assert record is not None
        thumbnail = await session.get(MediaAsset, record.thumbnail_asset_id)
        assert thumbnail is not None
        assert thumbnail.kind == "thumbnail"
        assert thumbnail.status == "degraded"
        assert thumbnail.object_key == f"{original.object_key}.thumb.jpg"

    # 失败不写对象。
    assert storage.object_count == 1

    failed = _events(caplog, EVENT_MEDIA_THUMBNAIL_FAILED)
    assert failed, "缩略图失败必须留下降级事件，不得静默"
    event = failed[-1]
    assert event["asset_id"] == original.asset_id
    assert event["task_id"] == task_id
    assert event["user_id"] == owner.id
    assert event["error_class"]
    assert event["level"] == "warning"
    assert "not-an-image" not in json.dumps(event)


@pytest.mark.asyncio
async def test_history_returns_degraded_when_thumbnail_asset_is_not_available(
    client, session_factory, users, storage
):
    owner = users["owner"]
    original = await _seed_asset(session_factory, storage, owner.id)
    degraded_asset_id = generate_asset_id()
    async with session_factory() as session:
        session.add(
            MediaAsset(
                asset_id=degraded_asset_id,
                user_id=owner.id,
                kind="thumbnail",
                object_key=f"{original.object_key}.thumb.jpg",
                content_type="image/jpeg",
                size_bytes=0,
                checksum="",
                status="degraded",
            )
        )
        session.add(
            BodyAnalysisRecord(
                user_id=owner.id,
                image_asset_id=original.asset_id,
                thumbnail_asset_id=degraded_asset_id,
                result=_analysis_result(),
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/vision/{owner.id}/history",
        headers=_auth(owner.id),
    )

    assert response.status_code == 200
    item = response.json()["records"][0]
    assert item["image_url"].startswith("memory://media/")
    assert item["thumbnail_url"] is None
    assert item["degraded"] is True


@pytest.mark.asyncio
async def test_thumbnail_signing_failure_degrades_but_keeps_original_url(
    client, session_factory, users, storage
):
    owner = users["owner"]
    original = await _seed_asset(session_factory, storage, owner.id)
    thumbnail = await _seed_asset(session_factory, storage, owner.id, _png_bytes(700, 500))
    async with session_factory() as session:
        session.add(
            BodyAnalysisRecord(
                user_id=owner.id,
                image_asset_id=original.asset_id,
                thumbnail_asset_id=thumbnail.asset_id,
                result=_analysis_result(),
            )
        )
        await session.commit()

    previous = app.dependency_overrides[get_storage]

    class _ThumbnailFailingSignStorage(InMemoryStorage):
        async def sign(self, key, ttl_seconds):
            if key == thumbnail.object_key:
                raise StorageError("down")
            return await storage.sign(key, ttl_seconds)

    app.dependency_overrides[get_storage] = lambda: _ThumbnailFailingSignStorage()
    try:
        response = await client.get(
            f"/api/vision/{owner.id}/history",
            headers=_auth(owner.id),
        )
    finally:
        app.dependency_overrides[get_storage] = previous

    assert response.status_code == 200
    item = response.json()["records"][0]
    assert item["image_url"].startswith("memory://media/")
    assert item["thumbnail_url"] is None
    assert item["degraded"] is True

