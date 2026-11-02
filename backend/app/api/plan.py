"""训练计划路由：获取当前计划、生成新计划、难度调整"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    ensure_current_user_matches,
    get_current_user,
    require_current_user_api_key,
)
from app.models.adjustment_job import (
    ERROR_CODE_JOB_FORBIDDEN,
    ERROR_CODE_JOB_NOT_FOUND,
)
from app.models.user import User
from app.schemas.adjustment import (
    AdjustmentJobDetail,
    AdjustmentJobPending,
    AdjustmentJobSummary,
    AdjustmentLatestResponse,
    AdjustmentOutcomeResponse,
    AdjustmentResumeRequest,
    AdjustmentResumeResponse,
)
from app.schemas.plan import GeneratePlanRequest, PlanResponse, TodayWorkoutResponse
from app.services.plan.adjustment_job_service import (
    AdjustmentJobService,
    AdjustmentResumeRejected,
)
from app.services.plan.plan_service import PlanService
from app.services.user.user_service import UserService

router = APIRouter()


@router.get("/{user_id}/adjustments/latest", response_model=AdjustmentLatestResponse)
async def get_latest_adjustment(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取最近一次调整结论；没有记录时返回 outcome=null（与「方向为 keep」可区分）。"""
    ensure_current_user_matches(current_user, user_id)
    service = PlanService(db)
    record = await service.get_latest_adjustment(user_id)
    return AdjustmentLatestResponse(
        outcome=AdjustmentOutcomeResponse.from_record(record) if record else None
    )


@router.get(
    "/{user_id}/adjustments/jobs",
    response_model=list[AdjustmentJobSummary],
)
async def list_adjustment_jobs(
    user_id: int,
    limit: int = Query(20, ge=1, le=100, description="最多返回多少条，默认 20、上限 100"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """最近调整作业（倒序摘要）；读取只依赖数据库，进程重启后同样可查。"""
    ensure_current_user_matches(current_user, user_id)
    jobs = await AdjustmentJobService(db).list_jobs(user_id, limit=limit)
    return [AdjustmentJobSummary.from_job(job) for job in jobs]


# 字面量 pending 必须声明在 {job_id} 之前，避免被当成作业标识。
@router.get(
    "/{user_id}/adjustments/jobs/pending",
    response_model=list[AdjustmentJobPending],
)
async def list_pending_adjustment_jobs(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户未决作业（评估中 / 待选择）；无未决时返回 200 空列表。"""
    ensure_current_user_matches(current_user, user_id)
    jobs = await AdjustmentJobService(db).list_pending(user_id)
    return [AdjustmentJobPending.from_job(job) for job in jobs]


@router.get(
    "/{user_id}/adjustments/jobs/{job_id}",
    response_model=AdjustmentJobDetail,
)
async def get_adjustment_job(
    user_id: int,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """作业详情：五维小结、合并分、决策与计划前后差异。"""
    ensure_current_user_matches(current_user, user_id)
    service = AdjustmentJobService(db)
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ERROR_CODE_JOB_NOT_FOUND, "message": "找不到这条调整作业"},
        )
    # 作业存在但属于别人：403 且不返回任何结果内容（不区分「存在但无权」的细节）。
    if job.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail={"code": ERROR_CODE_JOB_FORBIDDEN, "message": "无权访问其他用户的调整作业"},
        )
    adjustment = await service.get_adjustment(job.adjustment_id)
    return AdjustmentJobDetail.from_job(job, adjustment)


@router.post(
    "/{user_id}/adjustments/jobs/{job_id}/resume",
    response_model=AdjustmentResumeResponse,
)
async def resume_adjustment_job(
    user_id: int,
    job_id: str,
    req: AdjustmentResumeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """用户三选一后恢复：按所选项落地并回看结果；重复同一选项幂等、改选项冲突。"""
    ensure_current_user_matches(current_user, user_id)
    service = AdjustmentJobService(db)
    try:
        job, adjustment = await service.resume(
            job_id=job_id,
            user_id=current_user.id,
            option_id=req.option_id,
        )
    except AdjustmentResumeRejected as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    detail = AdjustmentJobDetail.from_job(job, adjustment)
    return AdjustmentResumeResponse(**detail.model_dump())


@router.get("/{user_id}/adjustments/{adjustment_id}", response_model=AdjustmentOutcomeResponse)
async def get_adjustment(
    user_id: int,
    adjustment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按稳定标识读取「本次」调整的结论（同一计划多次调整时不会互相覆盖）。"""
    ensure_current_user_matches(current_user, user_id)
    service = PlanService(db)
    record = await service.get_adjustment(user_id, adjustment_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "adjustment_not_found", "message": "找不到这条调整记录"},
        )
    return AdjustmentOutcomeResponse.from_record(record)


@router.get("/{user_id}/current", response_model=PlanResponse)
async def get_current_plan(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户当前周训练计划（附解释字段：生成依据 + 最近一次调整）"""
    ensure_current_user_matches(current_user, user_id)
    service = PlanService(db)
    plan, explanation = await service.get_current_plan_with_explanation(user_id)
    if not plan:
        raise HTTPException(status_code=404, detail="暂无训练计划，请先完成体型分析")
    return PlanResponse(plan=plan, message="获取成功", explanation=explanation)


@router.post("/generate", response_model=PlanResponse)
async def generate_plan(
    req: GeneratePlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user_api_key),
):
    """生成训练计划：自动从用户表读取体型分析和档案，前端无需手动传"""
    ensure_current_user_matches(current_user, req.user_id)
    body_analysis = req.body_analysis
    profile = req.profile

    if not body_analysis or not profile:
        user_service = UserService(db)
        user = await user_service.get_user(req.user_id)
        if user:
            body_analysis = body_analysis or user.body_analysis
            profile = profile or user.profile

    service = PlanService(db)
    plan = await service.generate_plan(
        user_id=req.user_id,
        body_analysis=body_analysis,
        profile=profile,
        week_start=req.week_start or datetime.date.today(),
    )
    return PlanResponse(plan=plan, message="训练计划生成成功，开始燃烧吧！")


@router.get(
    "/{user_id}/today",
    response_model=TodayWorkoutResponse,
    response_model_exclude_none=True,
)
async def get_today_workout(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取今日训练安排（三态：训练日 / 休息日 / 无计划，用于首页与训练会话入口）"""
    ensure_current_user_matches(current_user, user_id)
    service = PlanService(db)
    return await service.get_today_state(user_id)
