"""媒体资产路由：原图上传（服务端中转）、元数据返回与短时签名读图。"""
import asyncio
import datetime
import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.media_errors import (
    asset_not_found,
    checksum_mismatch,
    image_invalid,
    storage_unavailable,
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.storage import Storage, StorageError, get_storage
from app.models.media_asset import MediaAsset
from app.models.user import User
from app.schemas.media import MediaAssetResponse, MediaAssetUrlResponse
from app.services.media.media_asset_service import (
    MediaAssetService,
    inspect_image_size,
    normalize_content_type,
    sha256_hex,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    """SQLite 返回 naive datetime；统一成 UTC 以便序列化。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _asset_response(asset: MediaAsset) -> MediaAssetResponse:
    return MediaAssetResponse(
        asset_id=asset.asset_id,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        width=asset.width,
        height=asset.height,
        checksum=asset.checksum,
        created_at=_as_utc(asset.created_at),
    )


def _normalized_client_checksum(raw: str | None) -> str | None:
    """归一化客户端摘要（允许 ``sha256:`` 前缀）。"""
    if raw is None:
        return None
    value = raw.strip().lower()
    if value.startswith("sha256:"):
        value = value[len("sha256:"):]
    return value or None


@router.post("/assets", response_model=MediaAssetResponse)
async def upload_asset(
    file: UploadFile = File(..., description="图片文件"),
    checksum: str | None = Form(None, description="可选的客户端 sha256 摘要"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
):
    """接收图片、校验可解码性、去重后写入对象存储并登记资产。

    本票只做「能不能解码」；白名单、大小、最小分辨率等完整校验矩阵由后续工单负责。
    """
    data = await file.read()
    content_type = normalize_content_type(file.content_type)

    try:
        width, height = await asyncio.to_thread(inspect_image_size, data)
    except Exception:
        raise image_invalid() from None

    computed = sha256_hex(data)
    supplied = _normalized_client_checksum(checksum)
    if supplied is not None and supplied != computed:
        raise checksum_mismatch()

    service = MediaAssetService(db, storage)
    existing = await service.find_available_original(current_user.id, computed)
    if existing is not None:
        return _asset_response(existing)

    filename = file.filename[:255] if file.filename else None
    try:
        asset = await service.create_original(
            user_id=current_user.id,
            data=data,
            content_type=content_type,
            checksum=computed,
            width=width,
            height=height,
            original_filename=filename,
        )
    except StorageError:
        logger.exception("媒体资产写入对象存储失败", extra={"user_id": current_user.id})
        raise storage_unavailable() from None

    await db.commit()
    await db.refresh(asset)
    return _asset_response(asset)


@router.get("/assets/{asset_id}/url", response_model=MediaAssetUrlResponse)
async def get_asset_url(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
):
    """校验归属后签发短时有效的原图链接；URL 与过期时间不落库。"""
    service = MediaAssetService(db, storage)
    asset = await service.get_available_owned(asset_id, current_user.id)
    if asset is None:
        raise asset_not_found()

    try:
        url, expires_at = await service.sign(asset)
    except StorageError:
        logger.exception("媒体资产签名失败", extra={"asset_id": asset_id})
        raise storage_unavailable() from None

    return MediaAssetUrlResponse(
        asset_id=asset.asset_id,
        kind=asset.kind,
        url=url,
        expires_at=expires_at,
        content_type=asset.content_type,
        width=asset.width,
        height=asset.height,
        size_bytes=asset.size_bytes,
    )
