"""体型分析路由：上传图片 → 异步分析 → 轮询结果 → 历史记录"""
import asyncio
import base64
import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from PIL import Image
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.security import ensure_current_user_matches, get_current_user
from app.models.body_analysis import BodyAnalysisRecord
from app.models.user import User
from app.schemas.vision import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeResultResponse,
    BodyAnalysisHistoryResponse,
    BodyAnalysisRecordResponse,
    BodyAnalysisResult,
)
from app.services.ai.vision_graph import VisionGraph
from app.services.user.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()

_tasks: dict[str, dict] = {}

THUMBNAIL_WIDTH = 200


def _make_thumbnail(image_base64: str) -> str:
    """将原图 base64 压缩为缩略图 base64"""
    raw = base64.b64decode(image_base64)
    img = Image.open(io.BytesIO(raw))
    ratio = THUMBNAIL_WIDTH / img.width
    img = img.resize((THUMBNAIL_WIDTH, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


@router.post("/analyze", response_model=AnalyzeResponse)
async def start_analyze(
    req: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """接收图片 base64，启动异步体型分析，返回 task_id 供前端轮询"""
    ensure_current_user_matches(current_user, req.user_id)
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "processing",
        "result": None,
        "error": None,
        "user_id": req.user_id,
    }
    asyncio.create_task(_run_analysis(task_id, req))
    return AnalyzeResponse(task_id=task_id, status="processing")


@router.get("/analyze/{task_id}", response_model=AnalyzeResultResponse)
async def get_analyze_result(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """轮询体型分析任务状态与结果"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    ensure_current_user_matches(current_user, task["user_id"])
    return AnalyzeResultResponse(
        task_id=task_id,
        status=task["status"],
        result=task["result"],
        error=task["error"],
    )


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
    """后台任务：分析 + 保存最新结果到用户表 + 插入历史记录"""
    async with AsyncSessionLocal() as db:
        try:
            graph = VisionGraph(user_id=req.user_id, db=db)
            result = await graph.run(image_base64=req.image_base64, profile=req.profile)
            _tasks[task_id] = {
                "status": "completed",
                "result": result,
                "error": None,
                "user_id": req.user_id,
            }

            user_service = UserService(db)
            await user_service.save_body_analysis(req.user_id, result.model_dump())

            try:
                thumbnail = _make_thumbnail(req.image_base64)
            except Exception:
                thumbnail = None

            history_record = BodyAnalysisRecord(
                user_id=req.user_id,
                image_thumbnail=thumbnail,
                result=result.model_dump(),
            )
            db.add(history_record)
            await db.commit()
        except Exception as e:
            logger.exception("体型分析失败: task_id=%s", task_id)
            _tasks[task_id] = {
                "status": "failed",
                "result": None,
                "error": str(e),
                "user_id": req.user_id,
            }
