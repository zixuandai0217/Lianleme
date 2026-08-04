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
from app.schemas.plan import GeneratePlanRequest, PlanResponse
from app.services.plan.plan_service import PlanService
from app.services.user.user_service import UserService

router = APIRouter()


@router.get("/{user_id}/current", response_model=PlanResponse)
async def get_current_plan(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户当前周训练计划"""
    ensure_current_user_matches(current_user, user_id)
    service = PlanService(db)
    plan = await service.get_current_plan(user_id)
    if not plan:
        raise HTTPException(status_code=404, detail="暂无训练计划，请先完成体型分析")
    return PlanResponse(plan=plan, message="获取成功")


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


@router.get("/{user_id}/today")
async def get_today_workout(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取今日训练任务（用于首页展示）"""
    ensure_current_user_matches(current_user, user_id)
    service = PlanService(db)
    today_workout = await service.get_today_workout(user_id)
    if not today_workout:
        return {"message": "今日休息，好好恢复", "is_rest_day": True}
    return today_workout
