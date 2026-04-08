"""体型分析路由：上传图片 → 异步分析 → 轮询结果"""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.vision import AnalyzeRequest, AnalyzeResponse, AnalyzeResultResponse
from app.services.ai.vision_graph import VisionGraph
from app.services.user.user_service import UserService

router = APIRouter()

# 简单内存任务缓存（生产环境替换为 Redis）
_tasks: dict[str, dict] = {}


@router.post("/analyze", response_model=AnalyzeResponse)
async def start_analyze(req: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """
    接收图片 base64，启动异步体型分析任务，
    立即返回 task_id，前端轮询 /analyze/{task_id} 获取结果
    """
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "processing", "result": None, "error": None}

    # 异步执行 LangGraph 分析流程
    asyncio.create_task(_run_analysis(task_id, req, db))
    return AnalyzeResponse(task_id=task_id, status="processing")


@router.get("/analyze/{task_id}", response_model=AnalyzeResultResponse)
async def get_analyze_result(task_id: str):
    """轮询体型分析任务状态与结果"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return AnalyzeResultResponse(
        task_id=task_id,
        status=task["status"],
        result=task["result"],
        error=task["error"],
    )


async def _run_analysis(task_id: str, req: AnalyzeRequest, db: AsyncSession):
    """后台执行体型分析 LangGraph 流程并更新任务状态"""
    try:
        graph = VisionGraph(user_id=req.user_id, db=db)
        result = await graph.run(image_base64=req.image_base64, profile=req.profile)
        _tasks[task_id] = {"status": "completed", "result": result, "error": None}

        # 同步保存分析结果到用户档案
        user_service = UserService(db)
        await user_service.save_body_analysis(req.user_id, result.model_dump())
    except Exception as e:
        _tasks[task_id] = {"status": "failed", "result": None, "error": str(e)}
