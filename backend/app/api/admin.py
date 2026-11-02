"""管理后台路由：用户列表、系统统计（需管理员权限）"""
import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.schemas.admin import AdminUserFlag, AdminUserListItem, AdminUserListResponse, AdminUserSort
from app.services.admin import user_directory

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


@router.get("/users", response_model=AdminUserListResponse)
async def admin_users(
    q: str | None = Query(
        None,
        max_length=128,
        description="关键字：模糊匹配昵称/邮箱/openid，纯数字额外精确匹配用户 ID（精确命中排前）",
    ),
    has_plan: bool | None = Query(None, description="是否有训练计划"),
    registered_from: datetime.datetime | None = Query(
        None,
        description="注册时间下界（含）。不带时区的值按 UTC 解释；本地日界需由调用方换算为 UTC",
    ),
    registered_to: datetime.datetime | None = Query(
        None, description="注册时间上界（不含）。不带时区的值按 UTC 解释"
    ),
    checkins_min: int | None = Query(None, ge=0, description="累计打卡数下限（含）"),
    checkins_max: int | None = Query(None, ge=0, description="累计打卡数上限（含）"),
    active_within_days: int | None = Query(
        None, ge=0, description="最近 N 天内有活跃（业务事件时间最大值）"
    ),
    is_admin: bool | None = Query(None, description="是否管理员"),
    has_api_key: bool | None = Query(None, description="是否已配置自己的 LLM API Key"),
    flag: list[AdminUserFlag] | None = Query(
        None, description="需关注标记，可多选；多选为并集（任一命中即返回）"
    ),
    sort: AdminUserSort = Query("registered_desc", description="排序固定枚举"),
    page: int = Query(1, ge=1),
    page_size: int = Query(
        20, ge=1, le=100, description="每页条数，默认 20，超过上限 100 返回 422"
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserListResponse:
    """用户列表：搜索 / 组合筛选 / 排序 / 分页 + 服务端派生字段（只读，身份只来自 token）。

    派生字段（是否有计划、打卡统计、最近活跃、需关注标记）由一次聚合查询集算出，
    查询次数不随当页用户数增长。响应中的 openid / 邮箱一律掩码，且不含密码哈希与
    加密 Key 字段。
    """
    items, total = await user_directory.list_users(
        db,
        q=q,
        has_plan=has_plan,
        registered_from=registered_from,
        registered_to=registered_to,
        checkins_min=checkins_min,
        checkins_max=checkins_max,
        active_within_days=active_within_days,
        is_admin=is_admin,
        has_api_key=has_api_key,
        flags=flag,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return AdminUserListResponse(
        items=[AdminUserListItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
