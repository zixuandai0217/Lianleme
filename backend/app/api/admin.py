"""管理后台路由：用户列表、CSV 导出、导出审计、系统统计（需管理员权限）"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.schemas.admin import (
    AdminExportAuditItem,
    AdminExportAuditListResponse,
    AdminUserFlag,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserSort,
)
from app.services.admin import export as export_service
from app.services.admin import user_directory

router = APIRouter()


def directory_filters(
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
) -> user_directory.DirectoryFilters:
    """列表与导出共用的筛选参数：导出必须与列表应用完全相同的条件。

    身份只来自 token；旧的 ``user_id`` 查询参数继续被忽略（不参与筛选）。
    """
    return user_directory.DirectoryFilters(
        q=q,
        has_plan=has_plan,
        registered_from=registered_from,
        registered_to=registered_to,
        checkins_min=checkins_min,
        checkins_max=checkins_max,
        active_within_days=active_within_days,
        is_admin=is_admin,
        has_api_key=has_api_key,
        flags=tuple(flag) if flag else None,
        sort=sort,
    )


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
    filters: user_directory.DirectoryFilters = Depends(directory_filters),
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
        db, **filters.as_kwargs(), page=page, page_size=page_size
    )
    return AdminUserListResponse(
        items=[AdminUserListItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# 注意：本路由必须声明在将来可能新增的 ``/users/{user_id}`` 之前，
# 否则 "export" 会被当成用户 ID 解析（Starlette 按声明顺序匹配）。
@router.get("/users/export")
async def admin_users_export(
    filters: user_directory.DirectoryFilters = Depends(directory_filters),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """按当前筛选条件导出 CSV（只读，身份只来自 token）。

    与列表使用同一套筛选 / 排序，但不带分页；编码为 UTF-8 with BOM，首行固定中文
    表头。行数超过上限时返回 400 并要求收窄筛选，**不会**产出被截断的文件；筛选
    结果为 0 行时返回仅表头的文件。每次尝试（成功或被拒）都写一条审计记录。
    """
    result = await export_service.run_export(
        db,
        operator_id=admin.id,
        filters=filters,
        limit=settings.ADMIN_EXPORT_ROW_LIMIT,
    )
    if isinstance(result, export_service.ExportRejected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "export_row_limit_exceeded",
                "message": result.message,
            },
        )

    return Response(
        content=result.content,
        media_type=export_service.CSV_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/export-audits", response_model=AdminExportAuditListResponse)
async def admin_export_audits(
    page: int = Query(1, ge=1),
    page_size: int = Query(
        20, ge=1, le=100, description="每页条数，默认 20，超过上限 100 返回 422"
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminExportAuditListResponse:
    """导出审计（只读）：谁、在什么筛选条件下、导出了多少行、什么时候、成功还是被拒。

    记录只追加、不修改；成功导出的 ``rejection_reason`` 为空，被拒的导出带可读原因。
    """
    items, total = await export_service.list_audits(db, page=page, page_size=page_size)
    return AdminExportAuditListResponse(
        items=[AdminExportAuditItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
