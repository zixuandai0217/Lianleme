"""体型分析路由：创建持久任务 → 异步分析 → 轮询数据库事实 → 历史记录"""
import asyncio
import base64
import datetime
import io
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from PIL import Image
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.logging import (
    EVENT_TASK_COMPLETED,
    EVENT_TASK_CREATED,
    EVENT_TASK_FAILED,
    EVENT_TASK_STARTED,
    log_event,
)
from app.core.request_context import bind_request_context, get_request_id
from app.core.security import (
    ensure_current_user_matches,
    get_current_user,
    require_current_user_api_key,
)
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
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
from app.services.user.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()

THUMBNAIL_WIDTH = 200

# 终态一经写入不再改写；pending / processing 在过期时间之后对外视为 expired。
_ACTIVE_STATUSES = frozenset({"pending", "processing"})

_ERROR_MESSAGES = {
    "provider_auth_failed": "AI 服务鉴权失败，请检查 API Key 配置后重试",
    "provider_rate_limited": "AI 服务当前请求较多，请稍后重试",
    "provider_timeout": "分析超时，请稍后重试",
    "output_unparsable": "分析结果无法解析，请重新发起",
    "image_invalid": "照片无法识别，请换一张清晰的全身照",
    "storage_unavailable": "分析结果暂时无法保存，请稍后重试",
    "retry_exhausted": "多次重试后仍未完成分析，请重新发起",
    "task_expired": "分析任务已过期，请重新发起",
    "internal_error": "AI 服务暂时不可用，请稍后重试",
}

_RETRYABLE = {
    "provider_auth_failed": False,
    "provider_rate_limited": True,
    "provider_timeout": True,
    "output_unparsable": True,
    "image_invalid": False,
    "storage_unavailable": True,
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
        code = "image_invalid"
    elif any(hint in raw for hint in ("parse", "json", "output parser")):
        code = "output_unparsable"
    else:
        code = "internal_error"
    return code, _ERROR_MESSAGES[code], _RETRYABLE[code]


def _make_thumbnail(image_base64: str) -> str:
    """将原图 base64 压缩为缩略图 base64"""
    raw = base64.b64decode(image_base64)
    img = Image.open(io.BytesIO(raw))
    ratio = THUMBNAIL_WIDTH / img.width
    img = img.resize((THUMBNAIL_WIDTH, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


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
):
    """登记持久任务后启动异步分析；Key 前置校验在创建之前完成。"""
    ensure_current_user_matches(current_user, req.user_id)

    now = _utc_now()
    task = AnalysisTask(
        task_id=secrets.token_hex(16),
        user_id=req.user_id,
        status="pending",
        stage="queued",
        attempt=0,
        progress=0,
        request_id=get_request_id(),
        input_image_base64=req.image_base64,
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
                "code": "storage_unavailable",
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
    asyncio.create_task(_run_analysis(task.task_id, req))

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
):
    """获取用户体型分析历史（倒序）"""
    ensure_current_user_matches(current_user, user_id)
    result = await db.execute(
        select(BodyAnalysisRecord)
        .where(BodyAnalysisRecord.user_id == user_id)
        .order_by(desc(BodyAnalysisRecord.created_at))
        .limit(limit)
    )
    records = list(result.scalars().all())
    items = [
        BodyAnalysisRecordResponse(
            id=r.id,
            image_thumbnail=r.image_thumbnail,
            result=BodyAnalysisResult(**r.result),
            created_at=r.created_at,
        )
        for r in records
    ]
    return BodyAnalysisHistoryResponse(records=items, total=len(items))


@router.get("/record/{record_id}", response_model=BodyAnalysisRecordResponse)
async def get_analysis_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查看单条分析记录完整详情"""
    result = await db.execute(
        select(BodyAnalysisRecord).where(BodyAnalysisRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    ensure_current_user_matches(current_user, record.user_id)
    return BodyAnalysisRecordResponse(
        id=record.id,
        image_thumbnail=record.image_thumbnail,
        result=BodyAnalysisResult(**record.result),
        created_at=record.created_at,
    )


async def _run_analysis(task_id: str, req: AnalyzeRequest):
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
        image_base64 = task.input_image_base64 or req.image_base64
        profile = task.input_profile if task.input_profile is not None else req.profile

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

                try:
                    thumbnail = _make_thumbnail(image_base64)
                except Exception:
                    thumbnail = None

                history_record = BodyAnalysisRecord(
                    user_id=user_id,
                    image_thumbnail=thumbnail,
                    result=result.model_dump(),
                )
                db.add(history_record)
                await db.flush()

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
                    code="storage_unavailable",
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
