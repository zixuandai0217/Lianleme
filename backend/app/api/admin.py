"""管理后台路由：用户列表、用户详情、CSV 导出、导出审计、系统统计（需管理员权限）"""
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
    ADMIN_USER_DETAIL_SECTIONS,
    AdminExportAuditItem,
    AdminExportAuditListResponse,
    AdminUserDetailResponse,
    AdminUserFlag,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserSort,
)
from app.services.admin import export as export_service
from app.services.admin import user_detail, user_directory

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


def _requested_sections(raw: list[str] | None) -> tuple[str, ...]:
    """Parse the ``sections`` parameter into the canonical section tuple.

    Both spellings are accepted: ``?sections=profile,usage`` and
    ``?sections=profile&sections=usage``. Omitted or blank means "all sections".
    Unknown names are a caller error (422) rather than silently ignored, so a typo
    cannot make an operations page look like a user has no data.
    """
    if not raw:
        return ADMIN_USER_DETAIL_SECTIONS

    names = {part.strip() for value in raw for part in value.split(",") if part.strip()}
    if not names:
        return ADMIN_USER_DETAIL_SECTIONS

    unknown = names - set(ADMIN_USER_DETAIL_SECTIONS)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unknown_section",
                "message": f"不支持的分区：{', '.join(sorted(unknown))}",
                "supported": list(ADMIN_USER_DETAIL_SECTIONS),
            },
        )
    return tuple(section for section in ADMIN_USER_DETAIL_SECTIONS if section in names)


# 注意：本路由必须声明在 ``/users/export`` 之后，否则 "export" 会被当成用户 ID 解析。
@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    response_model_exclude_unset=True,
)
async def admin_user_detail(
    user_id: int,
    sections: list[str] | None = Query(
        None,
        description=(
            "要返回的分区，逗号分隔或重复参数均可；省略或留空返回全部分区。"
            "支持：profile / body_analysis / plan / checkins / weights / timeline / usage"
        ),
    ),
    page: int = Query(1, ge=1, description="timeline 分区页码（其余分区不分页）"),
    page_size: int = Query(
        20, ge=1, le=100, description="timeline 分区每页条数，默认 20，上限 100"
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserDetailResponse:
    """单个用户的运营详情（只读，身份只来自 token）。

    按 ``sections`` 组织成一个聚合响应：档案与账号状态、最近一次体型分析、当前计划与
    最近一次调整（复用计划解释投影）、近 90 天打卡序列与连续天数、近 90 天体重序列与
    频率、由既有数据派生的行为轨迹（分页）、AI 使用情况。未请求的分区整个不出现；
    请求了但数据源为空的分区为 null（``checkins`` / ``weights`` / ``timeline`` / ``usage``
    恒为对象，只是内容为空），所以「没请求」与「没有数据」可区分。缺计划、缺分析、
    缺体重的用户照常返回 200，只有未知用户 ID 是 404。

    脱敏在接口层完成：openid 前 6 后 4、邮箱本地部分掩码，API Key 只暴露状态与
    provider 名称，密码哈希与加密 Key 既不被查询也不进入响应模型。``page`` /
    ``page_size`` 只作用于 ``timeline`` 分区。
    """
    payload = await user_detail.get_user_detail(
        db,
        user_id,
        sections=_requested_sections(sections),
        timeline_page=page,
        timeline_page_size=page_size,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return AdminUserDetailResponse(**payload)
