"""
饮食计划路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, date
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.diet_plan import DietPlan
from app.models.diet_log import DietLog
from app.schemas.diet import (
    DietPlanGenerateRequest,
    DietPlanResponse,
    DietLogCreateRequest,
    DietLogResponse
)
from app.schemas.common import APIResponse
from app.api.deps import get_current_user
from app.core.ai_service import ai_service
from app.core.calculator import calculate_all, calculate_age

router = APIRouter()


@router.get("/today", response_model=DietPlanResponse, summary="获取今日饮食计划")
async def get_today_diet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户今日的饮食计划"""
    today = date.today()

    result = await db.execute(
        select(DietPlan)
        .where(DietPlan.user_id == current_user.id, DietPlan.plan_date == today)
    )
    diet_plan = result.scalar_one_or_none()

    if not diet_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="今日饮食计划不存在，请先生成"
        )

    return DietPlanResponse.model_validate(diet_plan)


@router.post("/generate", response_model=DietPlanResponse, summary="AI 生成饮食计划")
async def generate_diet(
    request: DietPlanGenerateRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """使用 AI 生成个性化饮食计划"""
    days = request.days if request else 7

    # 获取用户最新的身体数据
    profile_result = await db.execute(
        select(Profile)
        .where(Profile.user_id == current_user.id)
        .order_by(desc(Profile.recorded_at))
        .limit(1)
    )
    profile = profile_result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先录入身体数据"
        )

    # 计算营养需求
    age = calculate_age(str(profile.recorded_at)) if profile.recorded_at else 30
    nutrition = calculate_all(
        weight=profile.weight,
        height=profile.height,
        age=age,
        gender=current_user.gender or 1,
        activity_level=profile.activity_level or "moderate",
        goal_type=profile.goal_type or "lose_weight",
        weekly_goal=profile.weekly_goal or 0.5
    )

    # 构建用户数据
    user_data = {
        "gender": current_user.gender or 1,
        "height": profile.height,
        "weight": profile.weight,
        "age": age,
        "goal_type": profile.goal_type,
        "weekly_goal": profile.weekly_goal,
        "activity_level": profile.activity_level,
        "bmr": nutrition["bmr"],
        "tdee": nutrition["tdee"],
        "target_calories": nutrition["target_calories"],
        "allergies": profile.allergies or [],
        "preferences": profile.preferences or [],
        "avoid_foods": []
    }

    # 调用 AI 生成饮食计划
    plan_data = await ai_service.generate_diet_plan(user_data)

    # 保存到数据库
    diet_plan = DietPlan(
        user_id=current_user.id,
        profile_id=profile.id,
        daily_calories=plan_data.get("dailyCalories", int(nutrition["target_calories"])),
        protein=plan_data.get("protein", nutrition["protein"]),
        carbohydrates=plan_data.get("carbohydrates", nutrition["carbohydrates"]),
        fat=plan_data.get("fat", nutrition["fat"]),
        water=plan_data.get("water", 2000),
        meals=plan_data.get("meals", {}),
        preferences=profile.preferences,
        avoid_foods=profile.allergies,
        plan_date=date.today(),
        generated_by="AI"
    )

    db.add(diet_plan)
    await db.commit()
    await db.refresh(diet_plan)

    return DietPlanResponse.model_validate(diet_plan)


@router.get("/plans", response_model=List[DietPlanResponse], summary="获取饮食计划列表")
async def get_diet_plans(
    limit: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户饮食计划列表"""
    limit = min(limit, 30)

    result = await db.execute(
        select(DietPlan)
        .where(DietPlan.user_id == current_user.id)
        .order_by(desc(DietPlan.plan_date))
        .limit(limit)
    )
    plans = result.scalars().all()

    return [DietPlanResponse.model_validate(p) for p in plans]


@router.get("/logs", response_model=List[DietLogResponse], summary="获取饮食记录")
async def get_diet_logs(
    start_date: date = None,
    end_date: date = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户饮食记录"""
    query = select(DietLog).where(DietLog.user_id == current_user.id)

    if start_date:
        query = query.where(DietLog.log_date >= start_date)
    if end_date:
        query = query.where(DietLog.log_date <= end_date)

    query = query.order_by(desc(DietLog.log_date))
    result = await db.execute(query)
    logs = result.scalars().all()

    return [DietLogResponse.model_validate(log) for log in logs]


@router.post("/logs", response_model=DietLogResponse, summary="创建饮食记录")
async def create_diet_log(
    request: DietLogCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建饮食记录"""
    # 计算总营养
    total_calories = sum(f.get("calories", 0) for f in request.foods)
    total_protein = sum(f.get("protein", 0) for f in request.foods)
    total_carbs = sum(f.get("carbs", 0) for f in request.foods)
    total_fat = sum(f.get("fat", 0) for f in request.foods)

    diet_log = DietLog(
        user_id=current_user.id,
        log_date=request.log_date,
        meal_type=request.meal_type,
        foods=request.foods,
        total_calories=total_calories,
        total_protein=total_protein,
        total_carbs=total_carbs,
        total_fat=total_fat,
        image_url=request.image_url,
        notes=request.notes
    )

    db.add(diet_log)
    await db.commit()
    await db.refresh(diet_log)

    return DietLogResponse.model_validate(diet_log)
