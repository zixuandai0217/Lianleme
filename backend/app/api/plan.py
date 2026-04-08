"""训练计划路由：获取当前计划、生成新计划、难度调整"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.plan import GeneratePlanRequest, PlanResponse
from app.services.plan.plan_service import PlanService

router = APIRouter()


@router.get("/{user_id}/current", response_model=PlanResponse)
async def get_current_plan(user_id: int, db: AsyncSession = Depends(get_db)):
    """获取用户当前周训练计划"""
    service = PlanService(db)
    plan = await service.get_current_plan(user_id)
    if not plan:
        raise HTTPException(status_code=404, detail="暂无训练计划，请先完成体型分析")
    return PlanResponse(plan=plan, message="获取成功")


@router.post("/generate", response_model=PlanResponse)
async def generate_plan(req: GeneratePlanRequest, db: AsyncSession = Depends(get_db)):
    """根据体型分析结果和用户档案生成个性化训练计划"""
    service = PlanService(db)
    plan = await service.generate_plan(
        user_id=req.user_id,
        body_analysis=req.body_analysis,
        profile=req.profile,
        week_start=req.week_start or datetime.date.today(),
    )
    return PlanResponse(plan=plan, message="训练计划生成成功，开始燃烧吧！")


@router.get("/{user_id}/today")
async def get_today_workout(user_id: int, db: AsyncSession = Depends(get_db)):
    """获取今日训练任务（用于首页展示）"""
    service = PlanService(db)
    today_workout = await service.get_today_workout(user_id)
    if not today_workout:
        return {"message": "今日休息，好好恢复", "is_rest_day": True}
    return today_workout
