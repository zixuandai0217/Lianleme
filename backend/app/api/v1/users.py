"""
用户路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sql_delete
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.diet_plan import DietPlan
from app.models.diet_log import DietLog
from app.models.workout_plan import WorkoutPlan
from app.models.workout_log import WorkoutLog
from app.models.daily_stats import DailyStat
from app.models.chat_message import ChatMessage
from app.schemas.user import (
    UserResponse,
    UserProfileUpdateRequest,
    UserProfileResponse
)
from app.schemas.common import APIResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/profile", response_model=UserProfileResponse, summary="获取用户资料")
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户详细资料"""
    from app.schemas.profile import ProfileResponse

    # 获取当前身体数据
    current_profile = None
    if current_user.current_profile_id:
        from app.models.profile import Profile
        current_profile = await db.get(Profile, current_user.current_profile_id)

    return UserProfileResponse(
        user=UserResponse.model_validate(current_user),
        current_profile=ProfileResponse.model_validate(current_profile) if current_profile else None
    )


@router.put("/profile", response_model=UserResponse, summary="更新用户资料")
async def update_user_profile(
    request: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新用户个人资料"""
    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return UserResponse.model_validate(current_user)


@router.delete("/account", response_model=APIResponse, summary="注销账号")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    注销用户账号并删除所有个人数据

    注意：此操作不可恢复，将删除：
    - 用户基本信息
    - 所有身体数据记录
    - 所有饮食计划和记录
    - 所有运动计划和记录
    - 所有统计数据
    - 所有聊天记录
    """
    user_id = current_user.id

    # 删除所有关联数据（顺序很重要，先删除外键依赖的表）
    await db.execute(sql_delete(ChatMessage).where(ChatMessage.user_id == user_id))
    await db.execute(sql_delete(DietLog).where(DietLog.user_id == user_id))
    await db.execute(sql_delete(DietPlan).where(DietPlan.user_id == user_id))
    await db.execute(sql_delete(WorkoutLog).where(WorkoutLog.user_id == user_id))
    await db.execute(sql_delete(WorkoutPlan).where(WorkoutPlan.user_id == user_id))
    await db.execute(sql_delete(DailyStat).where(DailyStat.user_id == user_id))
    await db.execute(sql_delete(Profile).where(Profile.user_id == user_id))

    # 最后删除用户
    await db.execute(sql_delete(User).where(User.id == user_id))
    await db.commit()

    return APIResponse(message="账号及所有个人数据已删除")


@router.post("/export-data", response_model=dict, summary="导出个人数据")
async def export_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    导出用户的所有个人数据

    返回 JSON 格式的数据，包括：
    - 用户信息
    - 身体数据历史
    - 饮食计划和记录
    - 运动计划和记录
    - 聊天记录
    """
    from sqlalchemy import select

    user_id = current_user.id

    # 获取身体数据历史
    profiles_result = await db.execute(
        select(Profile).where(Profile.user_id == user_id).order_by(Profile.recorded_at.desc())
    )
    profiles = [
        {
            "id": p.id,
            "height": p.height,
            "weight": p.weight,
            "body_fat_rate": p.body_fat_rate,
            "bmi": p.bmi,
            "goal_type": p.goal_type,
            "recorded_at": p.recorded_at.isoformat() if p.recorded_at else None
        }
        for p in profiles_result.scalars().all()
    ]

    # 获取饮食记录（最近 30 条）
    diet_logs_result = await db.execute(
        select(DietLog).where(DietLog.user_id == user_id).order_by(DietLog.log_date.desc()).limit(30)
    )
    diet_logs = [
        {
            "log_date": str(d.log_date),
            "meal_type": d.meal_type,
            "total_calories": d.total_calories,
            "foods": d.foods
        }
        for d in diet_logs_result.scalars().all()
    ]

    # 获取运动记录（最近 30 条）
    workout_logs_result = await db.execute(
        select(WorkoutLog).where(WorkoutLog.user_id == user_id).order_by(WorkoutLog.workout_date.desc()).limit(30)
    )
    workout_logs = [
        {
            "workout_date": str(d.workout_date),
            "name": d.name,
            "duration": d.duration,
            "calories_burned": d.calories_burned,
            "status": d.status
        }
        for d in workout_logs_result.scalars().all()
    ]

    return {
        "user": {
            "id": current_user.id,
            "nickname": current_user.nickname,
            "phone": current_user.phone,
            "gender": current_user.gender,
            "created_at": str(current_user.created_at) if current_user.created_at else None
        },
        "profiles": profiles,
        "diet_logs": diet_logs,
        "workout_logs": workout_logs,
        "summary": {
            "total_profiles": len(profiles),
            "total_diet_logs": len(diet_logs),
            "total_workout_logs": len(workout_logs)
        }
    }
