"""
身体数据路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.schemas.profile import (
    ProfileCreateRequest,
    ProfileUpdateRequest,
    ProfileResponse,
    ProfileHistoryResponse
)
from app.schemas.common import APIResponse
from app.api.deps import get_current_user
from app.core.calculator import calculate_bmi

router = APIRouter()


@router.get("/current", response_model=ProfileResponse, summary="获取最新身体数据")
async def get_current_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户最新的身体数据"""
    # 优先使用用户设置的当前 profile
    if current_user.current_profile_id:
        profile = await db.get(Profile, current_user.current_profile_id)
        if profile and profile.user_id == current_user.id:
            return ProfileResponse.model_validate(profile)

    # 否则获取最新的记录
    result = await db.execute(
        select(Profile)
        .where(Profile.user_id == current_user.id)
        .order_by(desc(Profile.recorded_at))
        .limit(1)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="暂无身体数据，请先录入"
        )

    return ProfileResponse.model_validate(profile)


@router.get("/history", response_model=ProfileHistoryResponse, summary="获取身体数据历史")
async def get_profile_history(
    limit: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户身体数据历史记录"""
    limit = min(limit, 100)

    result = await db.execute(
        select(Profile)
        .where(Profile.user_id == current_user.id)
        .order_by(desc(Profile.recorded_at))
        .limit(limit)
    )
    profiles = result.scalars().all()

    return ProfileHistoryResponse(
        total=len(profiles),
        profiles=[ProfileResponse.model_validate(p) for p in profiles]
    )


@router.post("", response_model=ProfileResponse, summary="创建身体数据记录")
async def create_profile(
    request: ProfileCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新的身体数据记录"""
    from datetime import datetime

    # 计算 BMI
    bmi = calculate_bmi(request.weight, request.height)

    profile = Profile(
        user_id=current_user.id,
        height=request.height,
        weight=request.weight,
        body_fat_rate=request.body_fat_rate,
        muscle_mass=request.muscle_mass,
        bmi=bmi,
        target_weight=request.target_weight,
        target_body_fat=request.target_body_fat,
        weekly_goal=request.weekly_goal,
        goal_type=request.goal_type,
        activity_level=request.activity_level,
        exercise_days_per_week=request.exercise_days_per_week,
        health_issues=request.health_issues,
        allergies=request.allergies,
        preferences=request.preferences,
        recorded_at=datetime.utcnow()
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    # 更新用户的 current_profile_id
    current_user.current_profile_id = profile.id
    await db.commit()

    return ProfileResponse.model_validate(profile)


@router.put("/{profile_id}", response_model=ProfileResponse, summary="更新身体数据")
async def update_profile(
    profile_id: int,
    request: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新身体数据记录"""
    profile = await db.get(Profile, profile_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )

    if profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此记录"
        )

    update_data = request.model_dump(exclude_unset=True)

    # 如果更新了身高体重，重新计算 BMI
    if "weight" in update_data or "height" in update_data:
        weight = update_data.get("weight", profile.weight)
        height = update_data.get("height", profile.height)
        update_data["bmi"] = calculate_bmi(weight, height)

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return ProfileResponse.model_validate(profile)


@router.delete("/{profile_id}", response_model=APIResponse, summary="删除身体数据")
async def delete_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除身体数据记录"""
    profile = await db.get(Profile, profile_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )

    if profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此记录"
        )

    await db.delete(profile)

    # 如果删除的是当前 profile，清空引用
    if current_user.current_profile_id == profile_id:
        current_user.current_profile_id = None

    await db.commit()

    return APIResponse(message="删除成功")
