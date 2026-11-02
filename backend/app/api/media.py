"""媒体资产路由：原图上传（校验 + 服务端中转）、签名读图、用户级清空与孤儿巡检。"""
import asyncio
import datetime
import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.media_errors import (
    asset_not_found,
    checksum_mismatch,
    raise_upload_rejected,
    storage_unavailable,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import (
    EVENT_MEDIA_UPLOAD_REJECTED,
    FIELD_CONTENT_TYPE,
    FIELD_ERROR_CODE,
    FIELD_SIZE_BYTES,
    FIELD_USER_ID,
    log_event,
)
from app.core.security import ensure_current_user_matches, get_current_admin, get_current_user
from app.core.storage import Storage, StorageError, get_storage
from app.models.media_asset import MediaAsset
from app.models.user import User
from app.schemas.media import (
    CleanupCountsResponse,
    MediaAssetResponse,
    MediaAssetUrlResponse,
    OrphanSweepResponse,
)
from app.services.media.cleanup_service import CleanupResult, CleanupService
from app.services.media.media_asset_service import (
    MediaAssetService,
    MediaValidationError,
    clean_image_bytes,
    normalize_content_type,
    sha256_hex,
    validate_declared_content_type,
    validate_upload_size,
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


def _log_upload_rejection(
    *, code: str, user_id: int, content_type: str, size_bytes: int
) -> None:
    """记录一次校验拒绝；只带稳定分类字段，不写图片内容与用户文本。"""
    log_event(
        logger,
        EVENT_MEDIA_UPLOAD_REJECTED,
        message="图片上传校验未通过",
        level=logging.WARNING,
        **{
            FIELD_USER_ID: user_id,
            FIELD_ERROR_CODE: code,
            FIELD_CONTENT_TYPE: content_type,
            FIELD_SIZE_BYTES: size_bytes,
        },
    )


@router.post("/assets", response_model=MediaAssetResponse)
async def upload_asset(
    file: UploadFile = File(..., description="图片文件"),
    checksum: str | None = Form(None, description="可选的客户端 sha256 摘要"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
):
    """接收图片、执行请求期校验矩阵、清理元数据后去重写入对象存储。

    校验失败（格式/大小/解码/动图/伪装格式/分辨率）一律不产生资产与任务；
    通过后按 EXIF 方向纠正像素并重新编码，存档字节不再携带任何 EXIF/GPS。
    """
    # 只读到上限多一个字节即可判定超限，避免把超大请求体整个读进内存。
    data = await file.read(settings.MEDIA_MAX_UPLOAD_BYTES + 1)
    content_type = normalize_content_type(file.content_type)

    try:
        validate_declared_content_type(content_type)
        validate_upload_size(len(data))
        cleaned = await asyncio.to_thread(clean_image_bytes, data, content_type)
    except MediaValidationError as exc:
        _log_upload_rejection(
            code=exc.code,
            user_id=current_user.id,
            content_type=content_type,
            size_bytes=len(data),
        )
        raise_upload_rejected(exc.code)

    # 客户端摘要用于核对传输完整性；去重与资产元数据一律以清理后的存档字节为准。
    supplied = _normalized_client_checksum(checksum)
    if supplied is not None and supplied != sha256_hex(data):
        raise checksum_mismatch()

    computed = sha256_hex(cleaned.data)
    service = MediaAssetService(db, storage)
    existing = await service.find_available_original(current_user.id, computed)
    if existing is not None:
        return _asset_response(existing)

    filename = file.filename[:255] if file.filename else None
    try:
        asset = await service.create_original(
            user_id=current_user.id,
            data=cleaned.data,
            content_type=cleaned.content_type,
            checksum=computed,
            width=cleaned.width,
            height=cleaned.height,
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


def _cleanup_counts(result: CleanupResult) -> CleanupCountsResponse:
    """清理结果 → 响应；计数是清理唯一的对外可见证据。"""
    return CleanupCountsResponse(
        deleted_objects=result.deleted_objects,
        deleted_assets=result.deleted_assets,
        batches=result.batches,
    )


@router.delete("/users/{user_id}/assets", response_model=CleanupCountsResponse)
async def purge_user_assets(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
):
    """按用户前缀清空其全部媒体资产（仅本人，其他人一律 403）。

    对象与资产行都按批删除、按批提交；重复执行返回全零，且只触碰该用户自己的
    前缀 ``{APP_ENV}/{user_id}/``，绝不会删除其他用户的任何对象。
    """
    ensure_current_user_matches(current_user, user_id)
    service = CleanupService(db, storage)
    try:
        result = await service.purge_user_assets(user_id)
    except StorageError:
        logger.exception("用户级媒体资产清理失败", extra={FIELD_USER_ID: user_id})
        raise storage_unavailable() from None
    return _cleanup_counts(result)


@router.post("/maintenance/sweep", response_model=OrphanSweepResponse)
async def sweep_orphan_assets(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
    storage: Storage = Depends(get_storage),
):
    """管理员手动触发一次孤儿巡检（单批，可重入）。

    正向删除超过宽限期的未被引用对象，反向把「资产在但对象丢」的行标记降级；
    单批数量受 ``MEDIA_CLEANUP_BATCH_SIZE`` 约束，返回计数供运维核对。
    """
    service = CleanupService(db, storage)
    try:
        result = await service.sweep_orphans()
    except StorageError:
        logger.exception("媒体资产孤儿巡检失败")
        raise storage_unavailable() from None
    return OrphanSweepResponse(
        scanned=result.scanned,
        deleted_orphans=result.deleted_objects,
        degraded_assets=result.degraded_assets,
        batches=result.batches,
        skipped_young=result.skipped_young,
    )
