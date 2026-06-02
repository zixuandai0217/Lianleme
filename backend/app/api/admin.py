"""管理后台路由：用户列表、系统统计（需管理员权限）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.user import User
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord

router = APIRouter()


@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """系统统计概览：用户数、计划数、打卡数、7日活跃用户"""
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_plans = (await db.execute(select(func.count(TrainingPlan.id)))).scalar() or 0
    total_workouts = (await db.execute(select(func.count(WorkoutRecord.id)))).scalar() or 0

    import datetime
    week_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    active_q = select(func.count(func.distinct(WorkoutRecord.user_id))).where(
        WorkoutRecord.workout_date >= week_ago.date()
    )
    active_users_7d = (await db.execute(active_q)).scalar() or 0

    return {
        "total_users": total_users,
        "total_plans": total_plans,
        "total_workouts": total_workouts,
        "active_users_7d": active_users_7d,
    }


@router.get("/users")
async def admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """分页获取用户列表"""
    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    offset = (page - 1) * page_size

    users_q = select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(users_q)
    users = result.scalars().all()

    items = []
    for u in users:
        plan_q = select(func.count(TrainingPlan.id)).where(TrainingPlan.user_id == u.id)
        has_plan = ((await db.execute(plan_q)).scalar() or 0) > 0
        checkin_q = select(func.count(WorkoutRecord.id)).where(WorkoutRecord.user_id == u.id)
        total_checkins = (await db.execute(checkin_q)).scalar() or 0
        items.append({
            "id": u.id,
            "openid": u.openid,
            "nickname": u.nickname,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "has_plan": has_plan,
            "total_checkins": total_checkins,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
