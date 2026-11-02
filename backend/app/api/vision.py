"""体型分析路由：创建持久任务 → 异步分析 → 轮询数据库事实 → 历史记录"""
import asyncio
import base64
import datetime
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.media_errors import (
    MEDIA_ERROR_MESSAGES,
    asset_not_found,
    image_invalid,
    storage_unavailable,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.logging import (
    EVENT_MEDIA_THUMBNAIL_FAILED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_CREATED,
    EVENT_TASK_FAILED,
    EVENT_TASK_STARTED,
    FIELD_ASSET_ID,
    FIELD_ERROR_CLASS,
    FIELD_FAILED,
    log_event,
)
from app.core.request_context import bind_request_context, get_request_id
from app.core.security import (
    ensure_current_user_matches,
    get_current_user,
    require_current_user_api_key,
)
from app.core.storage import Storage, StorageError, get_storage
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
from app.models.media_asset import ASSET_STATUS_AVAILABLE, MediaAsset
from app.models.user import User
from app.schemas.vision import (
    AnalyzeErrorResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeResultResponse,
    BodyAnalysisHistoryResponse,
    BodyAnalysisRecordResponse,
    BodyAnalysisResult,
)
from app.services.ai.vision_graph import VisionGraph
from app.services.analysis_task_executor import AnalysisTaskExecutor
from app.services.media.media_asset_service import (
    ERROR_CODE_IMAGE_INVALID,
    ERROR_CODE_STORAGE_UNAVAILABLE,
    MediaAssetService,
    ThumbnailGenerationError,
    decode_base64_image,
    inspect_image_size,
    sha256_hex,
    sniff_content_type,
    thumbnail_degraded_total,
)
from app.services.user.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()

# 终态一经写入不再改写；pending / processing 在过期时间之后对外视为 expired。
_ACTIVE_STATUSES = frozenset({"pending", "processing"})

_ERROR_MESSAGES = {
    "provider_auth_failed": "AI 服务鉴权失败，请检查 API Key 配置后重试",
    "provider_rate_limited": "AI 服务当前请求较多，请稍后重试",
    "provider_timeout": "分析超时，请稍后重试",
    "output_unparsable": "分析结果无法解析，请重新发起",
    ERROR_CODE_IMAGE_INVALID: MEDIA_ERROR_MESSAGES[ERROR_CODE_IMAGE_INVALID],
    ERROR_CODE_STORAGE_UNAVAILABLE: MEDIA_ERROR_MESSAGES[ERROR_CODE_STORAGE_UNAVAILABLE],
    "retry_exhausted": "多次重试后仍未完成分析，请重新发起",
    "task_expired": "分析任务已过期，请重新发起",
    "internal_error": "AI 服务暂时不可用，请稍后重试",
}

_RETRYABLE = {
    "provider_auth_failed": False,
    "provider_rate_limited": True,
    "provider_timeout": True,
    "output_unparsable": True,
    ERROR_CODE_IMAGE_INVALID: False,
    ERROR_CODE_STORAGE_UNAVAILABLE: True,
    "retry_exhausted": True,
    "task_expired": True,
    "internal_error": True,
}


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    """SQLite 返回 naive datetime；统一成 UTC 以便比较与序列化。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _classify_failure(exc: BaseException) -> tuple[str, str, bool]:
    """把上游异常收敛成稳定错误码 + 安全文案，供应商原文只进日志。"""
    raw = f"{type(exc).__name__}: {exc}".lower()

    if any(
        hint in raw
        for hint in (
            "401",
            "403",
            "unauthorized",
            "authentication",
            "invalid api key",
            "incorrect api key",
            "api key",
        )
    ):
        code = "provider_auth_failed"
    elif any(hint in raw for hint in ("429", "rate limit", "too many requests", "quota")):
        code = "provider_rate_limited"
    elif any(hint in raw for hint in ("timeout", "timed out", "deadline exceeded")):
        code = "provider_timeout"
    elif any(hint in raw for hint in ("image", "decode", "cannot identify", "invalid image")):
        code = ERROR_CODE_IMAGE_INVALID
    elif any(hint in raw for hint in ("parse", "json", "output parser")):
        code = "output_unparsable"
    else:
        code = "internal_error"
    return code, _ERROR_MESSAGES[code], _RETRYABLE[code]


async def _persist_inline_asset(
    service: MediaAssetService,
    user_id: int,
    image_base64: str,
) -> str:
    """兼容期内联图片先落成资产，再让任务只引用资产标识。"""
    try:
        data = decode_base64_image(image_base64)
    except ValueError:
        raise image_invalid() from None

    checksum = sha256_hex(data)
    existing = await service.find_available_original(user_id, checksum)
    if existing is not None:
        return existing.asset_id

    content_type = sniff_content_type(data)
    try:
        width, height = await asyncio.to_thread(inspect_image_size, data)
    except Exception:
        # 兼容期内联内容不因无法解码而拒绝（完整校验属于上传接口）；元数据留空。
        width, height = None, None

    asset = await service.create_original(
        user_id=user_id,
        data=data,
        content_type=content_type,
        checksum=checksum,
        width=width,
        height=height,
    )
    return asset.asset_id


async def _signed_asset_url(
    asset_id: str | None,
    service: MediaAssetService,
    assets: dict[str, MediaAsset],
    cache: dict[str, str],
) -> tuple[str | None, bool]:
    """按需签发单个资产链接；缺失、非可用或签名失败只降级这一条。"""
    if not asset_id:
        return None, False

    if asset_id in cache:
        return cache[asset_id], False

    asset = assets.get(asset_id)
    if asset is None:
        return None, True

    try:
        url, _ = await service.sign(asset)
    except Exception:
        logger.warning("历史记录图片签名失败，降级为空链接", extra={"asset_id": asset_id})
        return None, True

    cache[asset_id] = url
    return url, False


async def _record_response(
    record: BodyAnalysisRecord,
    service: MediaAssetService,
    assets: dict[str, MediaAsset],
    cache: dict[str, str],
) -> BodyAnalysisRecordResponse:
    """把历史/详情记录映射成响应；旧内联缩略图字段固定为空。

    缩略图与原始图分别签发；任一失败都把该条标记为降级，但绝不让整个列表失败。
    指向降级/缺失缩略图资产的记录返回空 URL + degraded=true；没有缩略图指针的
    旧记录保持 degraded=false。
    """
    image_url, image_degraded = await _signed_asset_url(
        record.image_asset_id, service, assets, cache
    )
    thumbnail_url, thumbnail_degraded = await _signed_asset_url(
        record.thumbnail_asset_id, service, assets, cache
    )
    return BodyAnalysisRecordResponse(
        id=record.id,
        image_thumbnail=None,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        image_asset_id=record.image_asset_id,
        thumbnail_asset_id=record.thumbnail_asset_id,
        degraded=image_degraded or thumbnail_degraded,
        result=BodyAnalysisResult(**record.result),
        created_at=_as_utc(record.created_at),
    )


def _task_status(task: AnalysisTask, now: datetime.datetime) -> str:
    """任务对外状态：进行中的任务超过过期时间即视为 expired（不写库）。"""
    if task.status in _ACTIVE_STATUSES:
        expires_at = _as_utc(task.expires_at)
        if expires_at is not None and expires_at <= now:
            return "expired"
    return task.status


def _task_response(task: AnalysisTask) -> AnalyzeResultResponse:
    now = _utc_now()
    status = _task_status(task, now)
    result = None
    error = None

    if status == "completed" and task.result:
        try:
            result = BodyAnalysisResult(**task.result)
        except Exception:
            logger.warning("分析任务结果无法按 schema 解析", extra={"task_id": task.task_id})
            status = "failed"
            error = AnalyzeErrorResponse(
                code="internal_error",
                message=_ERROR_MESSAGES["internal_error"],
                retryable=True,
            )
    elif status == "failed":
        if task.error_code in _ERROR_MESSAGES:
            code = task.error_code
            message = task.error_message or _ERROR_MESSAGES[code]
        else:
            # Unknown codes are legacy/corrupt data; never echo their message.
            code = "internal_error"
            message = _ERROR_MESSAGES[code]
        error = AnalyzeErrorResponse(
            code=code,
            message=message,
            retryable=bool(task.error_retryable),
        )
    elif status == "expired":
        error = AnalyzeErrorResponse(
            code="task_expired",
            message=_ERROR_MESSAGES["task_expired"],
            retryable=True,
        )

    return AnalyzeResultResponse(
        task_id=task.task_id,
        status=status,
        stage=task.stage or "queued",
        attempt=task.attempt or 0,
        progress=task.progress or 0,
        result=result,
        error=error,
        created_at=_as_utc(task.created_at),
        updated_at=_as_utc(task.updated_at),
        expires_at=_as_utc(task.expires_at),
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def start_analyze(
    req: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user_api_key),
    storage: Storage = Depends(get_storage),
):
    """登记持久任务后启动异步分析；Key 前置校验在创建之前完成。

    任务只引用媒体资产：资产标识直接校验归属，兼容期内联图片先落成资产，
    ``analysis_tasks.input_image_base64`` 不再写入任何图片内容。
    """
    ensure_current_user_matches(current_user, req.user_id)
    service = MediaAssetService(db, storage)

    if req.image_asset_id is not None:
        asset = await service.get_available_owned(req.image_asset_id, req.user_id)
        if asset is None:
            raise asset_not_found()
        image_asset_id = asset.asset_id
    else:
        try:
            image_asset_id = await _persist_inline_asset(
                service,
                req.user_id,
                req.image_base64 or "",
            )
        except StorageError:
            logger.exception("内联图片写入对象存储失败", extra={"user_id": req.user_id})
            raise storage_unavailable() from None

    now = _utc_now()
    task = AnalysisTask(
        task_id=secrets.token_hex(16),
        user_id=req.user_id,
        status="pending",
        stage="queued",
        attempt=0,
        progress=0,
        request_id=get_request_id(),
        input_image_base64=None,
        image_asset_id=image_asset_id,
        input_profile=req.profile,
        expires_at=now + datetime.timedelta(minutes=settings.ANALYSIS_TASK_TTL_MINUTES),
    )
    db.add(task)
    try:
        await db.commit()
        await db.refresh(task)
    except Exception:
        await db.rollback()
        logger.exception("分析任务写入数据库失败", extra={"user_id": req.user_id})
        raise HTTPException(
            status_code=500,
            detail={
                "code": ERROR_CODE_STORAGE_UNAVAILABLE,
                "message": "分析任务暂时无法创建，请稍后重试",
            },
        )

    log_event(
        logger,
        EVENT_TASK_CREATED,
        message="体型分析任务已创建",
        task_id=task.task_id,
        user_id=task.user_id,
        attempt=0,
    )
    asyncio.create_task(_run_analysis(task.task_id, req, storage))

    return AnalyzeResponse(
        task_id=task.task_id,
        status="pending",
        stage=task.stage,
        created_at=_as_utc(task.created_at),
        expires_at=_as_utc(task.expires_at),
        poll_interval_ms=settings.ANALYSIS_TASK_POLL_INTERVAL_MS,
        suggested_poll_interval_ms=settings.ANALYSIS_TASK_POLL_INTERVAL_MS,
    )


@router.get("/analyze/{task_id}", response_model=AnalyzeResultResponse)
async def get_analyze_result(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """只读数据库返回任务状态；过期返回 200 + expired，未知标识返回 404。"""
    task = await db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "task_not_found", "message": "任务不存在"},
        )
    ensure_current_user_matches(current_user, task.user_id)
    return _task_response(task)


@router.get("/{user_id}/history", response_model=BodyAnalysisHistoryResponse)
async def get_analysis_history(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
):
    """获取用户体型分析历史（倒序）；图片链接按需签发，失败只降级该条。"""
    ensure_current_user_matches(current_user, user_id)
    result = await db.execute(
        select(BodyAnalysisRecord)
        .where(BodyAnalysisRecord.user_id == user_id)
        .order_by(desc(BodyAnalysisRecord.created_at))
        .limit(limit)
    )
    records = list(result.scalars().all())
    service = MediaAssetService(db, storage)
    asset_ids = {
        asset_id
        for record in records
        for asset_id in (record.image_asset_id, record.thumbnail_asset_id)
        if asset_id
    }
    assets = await service.get_available_assets(asset_ids, current_user.id)
    cache: dict[str, str] = {}
    items = [
        await _record_response(record, service, assets, cache) for record in records
    ]
    return BodyAnalysisHistoryResponse(records=items, total=len(items))


@router.get("/record/{record_id}", response_model=BodyAnalysisRecordResponse)
async def get_analysis_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
):
    """查看单条分析记录完整详情；图片链接按需签发。"""
    result = await db.execute(
        select(BodyAnalysisRecord).where(BodyAnalysisRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    ensure_current_user_matches(current_user, record.user_id)
    service = MediaAssetService(db, storage)
    asset_ids = {
        asset_id
        for asset_id in (record.image_asset_id, record.thumbnail_asset_id)
        if asset_id
    }
    assets = await service.get_available_assets(asset_ids, current_user.id)
    return await _record_response(record, service, assets, {})


async def _attach_thumbnail(
    db: AsyncSession,
    storage: Storage,
    *,
    task_id: str,
    history_record_id: int,
    original_asset_id: str | None,
    user_id: int,
    attempt: int,
) -> None:
    """分析结果提交后生成缩略图并回填引用；任何失败都只降级该条历史记录。

    缩略图是分析结果的附属物：对象写入与资产行先落库，再回填历史/任务引用；
    失败时登记一行降级资产并记录 ``media.thumbnail.failed``，分析结果始终可读。
    """
    if not original_asset_id:
        return

    task = await db.get(AnalysisTask, task_id)
    record = await db.get(BodyAnalysisRecord, history_record_id)
    if task is None or record is None:
        return
    if record.thumbnail_asset_id:
        current = await db.get(MediaAsset, record.thumbnail_asset_id)
        if current is not None and current.status == ASSET_STATUS_AVAILABLE:
            return

    service = MediaAssetService(db, storage)
    failure: BaseException | None = None
    thumbnail: MediaAsset | None = None
    try:
        original = await service.get_available_owned(original_asset_id, user_id)
        if original is None:
            return
        thumbnail = await service.ensure_thumbnail(original)
    except ThumbnailGenerationError as exc:
        thumbnail = exc.degraded_asset
        failure = exc.__cause__ or exc
    except Exception as exc:
        await db.rollback()
        failure = exc

    if thumbnail is not None:
        try:
            # 第二个事务：缩略图资产行（对象已在上一步写好）。
            await db.commit()
            # 失败路径回滚过事务，重新读取指针对象，避免在过期实例上触发同步刷新。
            record = await db.get(BodyAnalysisRecord, history_record_id)
            task = await db.get(AnalysisTask, task_id)
            if record is not None:
                record.thumbnail_asset_id = thumbnail.asset_id
            if task is not None:
                task.thumbnail_asset_id = thumbnail.asset_id
            # 第三个事务：回填历史与任务的缩略图引用。
            await db.commit()
        except Exception as exc:
            await db.rollback()
            failure = failure or exc

    if failure is not None:
        # 只记录稳定分类与标识字段：不含图片字节、不含用户内容。
        log_event(
            logger,
            EVENT_MEDIA_THUMBNAIL_FAILED,
            message="缩略图生成失败，历史记录降级为占位图",
            level=logging.WARNING,
            **{
                FIELD_ASSET_ID: original_asset_id,
                FIELD_ERROR_CLASS: type(failure).__name__,
                FIELD_FAILED: thumbnail_degraded_total(),
            },
        )


async def _run_analysis(
    task_id: str,
    req: AnalyzeRequest,
    storage: Storage | None = None,
):
    """后台任务：从数据库恢复输入，执行分析并在同一事务写入历史与任务结果。"""
    started = time.perf_counter()
    request_id = get_request_id()
    user_id = req.user_id
    attempt = 1

    async with AsyncSessionLocal() as db:
        task = await db.get(AnalysisTask, task_id)
        if task is None:
            logger.warning("分析任务不存在，跳过执行", extra={"task_id": task_id})
            return
        if task.status in {"completed", "failed"} or _task_status(task, _utc_now()) == "expired":
            logger.info("分析任务已是终态或已过期，跳过执行", extra={"task_id": task_id})
            return

        # Conditional claim prevents duplicate delivery from executing the same task.
        claimed = await AnalysisTaskExecutor(lambda: AsyncSessionLocal()).claim_task(task_id, db)
        if claimed is None or claimed.task_id != task_id:
            logger.info("分析任务未被当前执行者认领，跳过执行", extra={"task_id": task_id})
            return
        task = claimed
        request_id = task.request_id or request_id
        user_id = task.user_id
        attempt = task.attempt or 1
        storage_port = storage or get_storage()
        if task.image_asset_id:
            asset = await db.get(MediaAsset, task.image_asset_id)
            if asset is None:
                await _mark_failed(
                    db,
                    task_id,
                    RuntimeError("media asset missing"),
                    request_id=request_id,
                    user_id=user_id,
                    attempt=attempt,
                    started=started,
                    code=ERROR_CODE_STORAGE_UNAVAILABLE,
                )
                return
            try:
                image_base64 = base64.b64encode(
                    await storage_port.read(asset.object_key)
                ).decode()
            except Exception as exc:
                await _mark_failed(
                    db,
                    task_id,
                    exc,
                    request_id=request_id,
                    user_id=user_id,
                    attempt=attempt,
                    started=started,
                    code=ERROR_CODE_STORAGE_UNAVAILABLE,
                )
                return
        else:
            # 旧任务仍可能只带内联内容；新任务绝不会写入这个字段。
            image_base64 = task.input_image_base64 or req.image_base64
        profile = task.input_profile if task.input_profile is not None else req.profile

        if not image_base64:
            await _mark_failed(
                db,
                task_id,
                RuntimeError("task carries no image input"),
                request_id=request_id,
                user_id=user_id,
                attempt=attempt,
                started=started,
                code=ERROR_CODE_IMAGE_INVALID,
            )
            return

        # 后台任务运行在独立上下文：重新注入触发请求的关联信息
        with bind_request_context(
            request_id=request_id,
            user_id=user_id,
            task_id=task_id,
            attempt=attempt,
        ):
            log_event(
                logger,
                EVENT_TASK_STARTED,
                message="体型分析任务开始执行",
                task_id=task_id,
                user_id=user_id,
                attempt=attempt,
            )

            try:
                task.status = "processing"
                task.stage = "vision"
                task.attempt = attempt
                task.progress = 10
                task.started_at = _utc_now()
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("分析任务无法进入执行状态", extra={"task_id": task_id})
                return

            try:
                graph = VisionGraph(user_id=user_id, db=db)
                result = await graph.run(image_base64=image_base64, profile=profile)
            except Exception as exc:
                await _mark_failed(
                    db,
                    task_id,
                    exc,
                    request_id=request_id,
                    user_id=user_id,
                    attempt=attempt,
                    started=started,
                )
                return

            # 成功路径：历史记录与任务完成状态一次事务提交，避免「半个成功」。
            try:
                task.stage = "persist"
                task.progress = 80
                await db.flush()

                user_service = UserService(db)
                await user_service.save_body_analysis(user_id, result.model_dump())

                history_record = BodyAnalysisRecord(
                    user_id=user_id,
                    image_thumbnail=None,
                    image_asset_id=task.image_asset_id,
                    thumbnail_asset_id=task.thumbnail_asset_id,
                    result=result.model_dump(),
                )
                db.add(history_record)
                await db.flush()
                history_record_id = history_record.id

                task.result = result.model_dump()
                task.history_record_id = history_record.id
                task.status = "completed"
                task.stage = "done"
                task.progress = 100
                task.error_code = None
                task.error_message = None
                task.error_retryable = None
                task.finished_at = _utc_now()
                await db.commit()
            except Exception as exc:
                await db.rollback()
                await _mark_failed(
                    db,
                    task_id,
                    exc,
                    request_id=request_id,
                    user_id=user_id,
                    attempt=attempt,
                    started=started,
                    code=ERROR_CODE_STORAGE_UNAVAILABLE,
                )
                return

            log_event(
                logger,
                EVENT_TASK_COMPLETED,
                message="体型分析任务完成",
                task_id=task_id,
                user_id=user_id,
                attempt=attempt,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )

            # 缩略图在结果提交后生成：失败只降级历史展示，不改写已完成的结论。
            await _attach_thumbnail(
                db,
                storage_port,
                task_id=task_id,
                history_record_id=history_record_id,
                original_asset_id=task.image_asset_id,
                user_id=user_id,
                attempt=attempt,
            )


async def _mark_failed(
    db: AsyncSession,
    task_id: str,
    exc: BaseException,
    *,
    request_id: str | None,
    user_id: int,
    attempt: int,
    started: float,
    code: str | None = None,
) -> None:
    """写入稳定错误码与安全文案；供应商原文只出现在结构化日志里。"""
    if code is None:
        code, message, retryable = _classify_failure(exc)
    else:
        message = _ERROR_MESSAGES[code]
        retryable = _RETRYABLE[code]

    try:
        task = await db.get(AnalysisTask, task_id)
        if task is not None:
            task.status = "failed"
            task.stage = "done"
            task.error_code = code
            task.error_message = message
            task.error_retryable = retryable
            task.finished_at = _utc_now()
            await db.commit()
        log_event(
            logger,
            EVENT_TASK_FAILED,
            message="体型分析任务失败",
            level=logging.ERROR,
            exc_info=True,
            task_id=task_id,
            user_id=user_id,
            attempt=attempt,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            error_code=code,
            error_class=type(exc).__name__,
        )
    except Exception:
        await db.rollback()
        logger.exception("分析任务失败状态无法写入数据库", extra={"task_id": task_id})
