"""
统计数据路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from datetime import datetime, date, timedelta
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.daily_stats import DailyStat
from app.models.diet_log import DietLog
from app.models.workout_log import WorkoutLog
from app.schemas.stats import (
    DailyStatResponse,
    SummaryStatsResponse,
    WeightTrendItem,
    WeightTrendResponse
)
from app.schemas.common import APIResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/daily", response_model=List[DailyStatResponse], summary="获取每日统计")
async def get_daily_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户每日统计数据"""
    # 默认最近 7 天
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=6)

    result = await db.execute(
        select(DailyStat)
        .where(
            DailyStat.user_id == current_user.id,
            DailyStat.stat_date >= start_date,
            DailyStat.stat_date <= end_date
        )
        .order_by(DailyStat.stat_date)
    )
    stats = result.scalars().all()

    return [DailyStatResponse.model_validate(s) for s in stats]


@router.get("/summary", response_model=SummaryStatsResponse, summary="获取汇总统计")
async def get_summary_stats(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取周期汇总统计"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    # 查询周期内的统计数据
    result = await db.execute(
        select(
            func.avg(DailyStat.calories_in).label("avg_calories_in"),
            func.avg(DailyStat.calories_out).label("avg_calories_out"),
            func.avg(DailyStat.net_calories).label("avg_net_calories"),
            func.count(DailyStat.id).label("total_days"),
            func.sum(
                case(
                    (DailyStat.diet_plan_completed == True, 1),
                    else_=0
                )
            ).label("diet_completed_days"),
            func.sum(
                case(
                    (DailyStat.workout_completed == True, 1),
                    else_=0
                )
            ).label("workout_completed_days"),
        )
        .where(
            DailyStat.user_id == current_user.id,
            DailyStat.stat_date >= start_date,
            DailyStat.stat_date <= end_date
        )
    )
    row = result.first()

    # 获取体重变化
    profile_result = await db.execute(
        select(Profile)
        .where(
            Profile.user_id == current_user.id,
            Profile.recorded_at >= datetime.combine(start_date, datetime.min.time())
        )
        .order_by(Profile.recorded_at)
    )
    profiles = profile_result.scalars().all()

    start_weight = profiles[0].weight if profiles else None
    end_weight = profiles[-1].weight if profiles else None
    weight_change = None
    if start_weight and end_weight:
        weight_change = round(end_weight - start_weight, 2)

    return SummaryStatsResponse(
        start_date=start_date,
        end_date=end_date,
        avg_calories_in=float(row.avg_calories_in or 0),
        avg_calories_out=float(row.avg_calories_out or 0),
        avg_net_calories=float(row.avg_net_calories or 0),
        total_days=row.total_days or 0,
        diet_completed_days=int(row.diet_completed_days or 0),
        workout_completed_days=int(row.workout_completed_days or 0),
        start_weight=start_weight,
        end_weight=end_weight,
        weight_change=weight_change
    )


@router.get("/trend", response_model=WeightTrendResponse, summary="获取体重趋势")
async def get_weight_trend(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取体重变化趋势"""
    start_date = date.today() - timedelta(days=days)

    result = await db.execute(
        select(Profile)
        .where(
            Profile.user_id == current_user.id,
            Profile.recorded_at >= datetime.combine(start_date, datetime.min.time())
        )
        .order_by(Profile.recorded_at)
    )
    profiles = result.scalars().all()

    if not profiles:
        return WeightTrendResponse(
            data=[],
            trend="stable"
        )

    # 构建趋势数据
    trend_data = [
        WeightTrendItem(
            date=p.recorded_at.date(),
            weight=p.weight,
            body_fat_rate=p.body_fat_rate
        )
        for p in profiles
    ]

    # 计算趋势
    if len(trend_data) >= 2:
        first_weight = trend_data[0].weight
        last_weight = trend_data[-1].weight
        change = last_weight - first_weight

        if change < -1:
            trend = "down"
        elif change > 1:
            trend = "up"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return WeightTrendResponse(
        data=trend_data,
        trend=trend
    )


@router.post("/update", response_model=APIResponse, summary="更新每日统计")
async def update_daily_stats(
    stat_date: date = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新每日统计数据

    自动聚合当天的饮食和运动记录
    """
    if not stat_date:
        stat_date = date.today()

    # 查询当天的饮食记录
    diet_result = await db.execute(
        select(
            func.sum(DietLog.total_calories).label("calories_in"),
            func.sum(DietLog.total_protein).label("protein_in"),
            func.sum(DietLog.total_carbs).label("carbs_in"),
            func.sum(DietLog.total_fat).label("fat_in"),
        )
        .where(
            DietLog.user_id == current_user.id,
            DietLog.log_date == stat_date
        )
    )
    diet_row = diet_result.first()

    # 查询当天的运动记录
    workout_result = await db.execute(
        select(
            func.sum(WorkoutLog.calories_burned).label("exercise_calories"),
            func.count(WorkoutLog.id).label("workout_count"),
        )
        .where(
            WorkoutLog.user_id == current_user.id,
            WorkoutLog.workout_date == stat_date
        )
    )
    workout_row = workout_result.first()

    # 获取用户的基础代谢（用于计算 TDEE）
    profile_result = await db.execute(
        select(Profile)
        .where(Profile.user_id == current_user.id)
        .order_by(desc(Profile.recorded_at))
        .limit(1)
    )
    profile = profile_result.scalar_one_or_none()

    # 估算静息消耗（简化计算：BMR ≈ 体重 * 24）
    resting_calories = (profile.weight * 24) if profile else 1500
    exercise_calories = workout_row.exercise_calories or 0
    calories_out = resting_calories + exercise_calories

    # 计算摄入
    calories_in = diet_row.calories_in or 0
    net_calories = calories_in - calories_out

    # 更新或创建统计记录
    daily_stat = await db.get(DailyStat, {"user_id": current_user.id, "stat_date": stat_date})

    if daily_stat:
        # 更新
        daily_stat.calories_in = calories_in
        daily_stat.protein_in = diet_row.protein_in or 0
        daily_stat.carbs_in = diet_row.carbs_in or 0
        daily_stat.fat_in = diet_row.fat_in or 0
        daily_stat.calories_out = calories_out
        daily_stat.exercise_calories = exercise_calories
        daily_stat.net_calories = net_calories
        daily_stat.workout_completed = (workout_row.workout_count or 0) > 0
        daily_stat.updated_at = datetime.utcnow()
    else:
        # 创建
        daily_stat = DailyStat(
            user_id=current_user.id,
            stat_date=stat_date,
            calories_in=calories_in,
            protein_in=diet_row.protein_in or 0,
            carbs_in=diet_row.carbs_in or 0,
            fat_in=diet_row.fat_in or 0,
            calories_out=calories_out,
            exercise_calories=exercise_calories,
            net_calories=net_calories,
            workout_completed=(workout_row.workout_count or 0) > 0
        )
        db.add(daily_stat)

    await db.commit()

    return APIResponse(message="统计已更新")
