"""训练计划路由：获取当前计划、生成新计划、难度调整"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    ensure_current_user_matches,
    get_current_user,
    require_current_user_api_key,
)
from app.models.user import User
from app.schemas.adjustment import AdjustmentLatestResponse, AdjustmentOutcomeResponse
from app.schemas.plan import GeneratePlanRequest, PlanResponse, TodayWorkoutResponse
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
