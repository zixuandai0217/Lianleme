"""
运动计划路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, date, timedelta
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.workout_plan import WorkoutPlan
from app.models.workout_log import WorkoutLog
from app.schemas.workout import (
    WorkoutPlanGenerateRequest,
    WorkoutPlanResponse,
    WorkoutLogCreateRequest,
    WorkoutLogResponse
)
from app.schemas.common import APIResponse
from app.api.deps import get_current_user
from app.core.ai_service import ai_service

router = APIRouter()


@router.get("/current", response_model=WorkoutPlanResponse, summary="获取当前运动计划")
async def get_current_workout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户当前的运动计划"""
    today = date.today()

    result = await db.execute(
        select(WorkoutPlan)
        .where(
            WorkoutPlan.user_id == current_user.id,
            WorkoutPlan.plan_start_date <= today,
            WorkoutPlan.plan_end_date >= today
        )
        .order_by(desc(WorkoutPlan.plan_start_date))
        .limit(1)
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前无有效运动计划，请先生成"
        )

    return WorkoutPlanResponse.model_validate(plan)


@router.post("/generate", response_model=WorkoutPlanResponse, summary="AI 生成运动计划")
async def generate_workout(
    request: WorkoutPlanGenerateRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """使用 AI 生成个性化运动计划"""
    weeks = request.weeks if request else 4
    days_per_week = request.days_per_week if request else 5

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

    # 构建用户数据
    user_data = {
        "gender": current_user.gender or 1,
        "height": profile.height,
        "weight": profile.weight,
        "goal_type": profile.goal_type or "lose_weight",
        "activity_level": profile.activity_level or "moderate",
        "exercise_days": days_per_week
    }

    # 调用 AI 生成运动计划
    plan_data = await ai_service.generate_workout_plan(user_data)

    # 计算计划日期
    start_date = date.today()
    end_date = start_date + timedelta(weeks=weeks)

    # 保存到数据库
    workout_plan = WorkoutPlan(
        user_id=current_user.id,
        weekly_workout_days=plan_data.get("weeklyWorkoutDays", days_per_week),
        estimated_calories_burn=plan_data.get("estimatedCaloriesBurn", 300),
        week_plan=plan_data.get("weekPlan", []),
        plan_start_date=start_date,
        plan_end_date=end_date,
        generated_by="AI"
    )

    db.add(workout_plan)
    await db.commit()
    await db.refresh(workout_plan)

    return WorkoutPlanResponse.model_validate(workout_plan)


@router.get("/plans", response_model=List[WorkoutPlanResponse], summary="获取运动计划列表")
async def get_workout_plans(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户运动计划列表"""
    limit = min(limit, 20)

    result = await db.execute(
        select(WorkoutPlan)
        .where(WorkoutPlan.user_id == current_user.id)
        .order_by(desc(WorkoutPlan.plan_start_date))
        .limit(limit)
    )
    plans = result.scalars().all()

    return [WorkoutPlanResponse.model_validate(p) for p in plans]


@router.get("/logs", response_model=List[WorkoutLogResponse], summary="获取运动记录")
async def get_workout_logs(
    start_date: date = None,
    end_date: date = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户运动记录"""
    query = select(WorkoutLog).where(WorkoutLog.user_id == current_user.id)

    if start_date:
        query = query.where(WorkoutLog.workout_date >= start_date)
    if end_date:
        query = query.where(WorkoutLog.workout_date <= end_date)

    query = query.order_by(desc(WorkoutLog.workout_date))
    result = await db.execute(query)
    logs = result.scalars().all()

    return [WorkoutLogResponse.model_validate(log) for log in logs]


@router.post("/logs", response_model=WorkoutLogResponse, summary="创建运动记录")
async def create_workout_log(
    request: WorkoutLogCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建运动记录"""
    workout_log = WorkoutLog(
        user_id=current_user.id,
        workout_date=request.workout_date,
        workout_type=request.workout_type,
        name=request.name,
        status=request.status,
        duration=request.duration,
        calories_burned=request.calories_burned,
        exercises_completed=request.exercises_completed,
        notes=request.notes
    )

    db.add(workout_log)
    await db.commit()
    await db.refresh(workout_log)

    return WorkoutLogResponse.model_validate(workout_log)


@router.put("/logs/{log_id}", response_model=WorkoutLogResponse, summary="更新运动记录")
async def update_workout_log(
    log_id: int,
    request: WorkoutLogCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新运动记录"""
    log = await db.get(WorkoutLog, log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此记录"
        )

    # 更新字段
    for field in ["workout_type", "name", "status", "duration", "calories_burned", "notes"]:
        value = getattr(request, field, None)
        if value is not None:
            setattr(log, field, value)

    if request.exercises_completed:
        log.exercises_completed = request.exercises_completed

    await db.commit()
    await db.refresh(log)

    return WorkoutLogResponse.model_validate(log)
