"""管理后台用户目录：搜索 / 筛选 / 排序 / 分页 + 服务端派生字段。

性能约定（AC4）：当页用户的派生字段由固定数量的聚合子查询一次算齐——一次列表请求
只发「计数」与「当页」两条业务 SQL，查询次数不随当页用户数增长（当前的 N+1 已消除）。
搜索用 LIKE 模糊匹配（前置通配符，走不了 B-tree 索引）；几千用户量级可接受，再上一个
量级时应评估 pg_trgm 之类的模糊索引，而不是在这里改成逐用户查询。

「最近活跃」口径：当前数据模型没有登录会话表，也没有 last_active_at 字段，因此把
「最近活跃」定义为下列业务事件时间的最大值：注册（users.created_at）、生成/更新计划、
打卡、体型分析、体重记录、陪练对话。它不是登录时间；需要精确登录时间时应单独加字段。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import ColumnElement, Select, Subquery, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_analysis import BodyAnalysisRecord
from app.models.chat_message import ChatMessageRecord
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord

# 需关注标记（服务端规则计算，可同时存在）
FLAG_NEW_NO_PLAN = "new_no_plan"
FLAG_PLANNED_NO_CHECKIN = "planned_no_checkin"
FLAG_INACTIVE_14D = "inactive_14d"
FLAG_NEVER_ANALYZED = "never_analyzed"
FLAG_API_KEY_MISSING = "api_key_missing"

ALL_FLAGS: tuple[str, ...] = (
    FLAG_NEW_NO_PLAN,
    FLAG_PLANNED_NO_CHECKIN,
    FLAG_INACTIVE_14D,
    FLAG_NEVER_ANALYZED,
    FLAG_API_KEY_MISSING,
)

# 排序固定枚举
SORT_REGISTERED_ASC = "registered_asc"
SORT_REGISTERED_DESC = "registered_desc"
SORT_LAST_ACTIVE_ASC = "last_active_asc"
SORT_LAST_ACTIVE_DESC = "last_active_desc"

ALL_SORTS: tuple[str, ...] = (
    SORT_REGISTERED_ASC,
    SORT_REGISTERED_DESC,
    SORT_LAST_ACTIVE_ASC,
    SORT_LAST_ACTIVE_DESC,
)

# 标记阈值（天）。SQL 过滤与 Python 标记计算共用同一组常量，避免两处口径漂移。
NEW_NO_PLAN_DAYS = 7
PLANNED_NO_CHECKIN_DAYS = 7
INACTIVE_DAYS = 14
NEVER_ANALYZED_DAYS = 3
CHECKINS_30D_DAYS = 30

_LIKE_ESCAPE = "\\"


def utc_now() -> dt.datetime:
    """Current UTC instant. Tests freeze this to keep day boundaries deterministic."""
    return dt.datetime.now(dt.timezone.utc)


def mask_openid(openid: str | None) -> str | None:
    """Mask an openid as ``first 6 + last 4``; short values are fully masked."""
    if not openid:
        return openid
    if len(openid) <= 10:
        return "*" * len(openid)
    return f"{openid[:6]}{'*' * (len(openid) - 10)}{openid[-4:]}"


def mask_email(email: str | None) -> str | None:
    """Mask the local part of an email, keeping its first character and the domain."""
    if not email:
        return email
    local, separator, domain = email.partition("@")
    if not separator:
        return f"{email[:1]}***"
    return f"{local[:1]}***@{domain}"


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input can never widen the pattern."""
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )


def _numeric_id(term: str) -> int | None:
    """Return the term as a user id when it is purely numeric."""
    if term.isdigit():
        return int(term)
    return None


def _as_utc(value: dt.datetime | None) -> dt.datetime | None:
    """Normalize a stored/derived timestamp (or filter bound) to aware UTC.

    Naive values are interpreted as UTC: the API takes instants, not local wall time.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _greatest(*expressions: Any) -> Any:
    """Portable scalar MAX over columns (NULLs lose), without dialect-specific functions."""
    result = expressions[0]
    for candidate in expressions[1:]:
        result = case(
            (result.is_(None), candidate),
            (candidate.is_(None), result),
            (result >= candidate, result),
            else_=candidate,
        )
    return result


def _has_api_key_expression() -> ColumnElement[Any]:
    """Whether a user configured their own provider key (never selects the ciphertext)."""
    return and_(User.llm_api_key.isnot(None), User.llm_api_key != "")


@dataclass(frozen=True)
class _Aggregates:
    """Per-user aggregates joined into the list query (one subquery per data source)."""

    plans: Subquery
    checkins: Subquery
    analyses: Subquery
    weights: Subquery
    chats: Subquery
    last_active: Any


def _build_aggregates(now: dt.datetime) -> _Aggregates:
    """Build the fixed set of per-user aggregate subqueries used by a list request."""
    checkin_cutoff = (now - dt.timedelta(days=CHECKINS_30D_DAYS)).date()

    # 最新计划的难度系数：ranked 里只留 rn=1 的难度，再由 max() 把它挑出来。
    ranked_plans = (
        select(
            TrainingPlan.user_id.label("user_id"),
            TrainingPlan.created_at.label("created_at"),
            TrainingPlan.difficulty_factor.label("difficulty_factor"),
            func.row_number()
            .over(
                partition_by=TrainingPlan.user_id,
                order_by=(TrainingPlan.created_at.desc(), TrainingPlan.id.desc()),
            )
            .label("recency_rank"),
        )
        .subquery("admin_plan_ranked")
    )
    plans = (
        select(
            ranked_plans.c.user_id.label("user_id"),
            func.count().label("plan_count"),
            func.max(ranked_plans.c.created_at).label("last_plan_at"),
            func.max(
                case(
                    (ranked_plans.c.recency_rank == 1, ranked_plans.c.difficulty_factor),
                    else_=None,
                )
            ).label("difficulty_factor"),
        )
        .group_by(ranked_plans.c.user_id)
        .subquery("admin_plan_agg")
    )

    checkins = (
        select(
            WorkoutRecord.user_id.label("user_id"),
            func.count().label("total_checkins"),
            func.sum(case((WorkoutRecord.workout_date >= checkin_cutoff, 1), else_=0)).label(
                "checkins_30d"
            ),
            func.max(WorkoutRecord.workout_date).label("last_checkin_date"),
            func.max(WorkoutRecord.created_at).label("last_checkin_at"),
        )
        .group_by(WorkoutRecord.user_id)
        .subquery("admin_checkin_agg")
    )

    analyses = (
        select(
            BodyAnalysisRecord.user_id.label("user_id"),
            func.count().label("analysis_count"),
            func.max(BodyAnalysisRecord.created_at).label("last_analysis_at"),
        )
        .group_by(BodyAnalysisRecord.user_id)
        .subquery("admin_analysis_agg")
    )

    weights = (
        select(
            WeightRecord.user_id.label("user_id"),
            func.max(WeightRecord.created_at).label("last_weight_at"),
        )
        .group_by(WeightRecord.user_id)
        .subquery("admin_weight_agg")
    )

    chats = (
        select(
            ChatMessageRecord.user_id.label("user_id"),
            func.max(ChatMessageRecord.created_at).label("last_chat_at"),
        )
        .group_by(ChatMessageRecord.user_id)
        .subquery("admin_chat_agg")
    )

    last_active = _greatest(
        User.created_at,
        plans.c.last_plan_at,
        checkins.c.last_checkin_at,
        analyses.c.last_analysis_at,
        weights.c.last_weight_at,
        chats.c.last_chat_at,
    )

    return _Aggregates(
        plans=plans,
        checkins=checkins,
        analyses=analyses,
        weights=weights,
        chats=chats,
        last_active=last_active,
    )


def _base_select(agg: _Aggregates) -> Select[Any]:
    """Rows for one page: identity/contact columns plus every derived field."""
    return (
        select(
            User.id.label("id"),
            User.nickname.label("nickname"),
            User.avatar_url.label("avatar_url"),
            User.openid.label("openid"),
            User.email.label("email"),
            User.is_admin.label("is_admin"),
            User.llm_provider.label("llm_provider"),
            _has_api_key_expression().label("has_api_key"),
            User.created_at.label("created_at"),
            User.body_analysis.isnot(None).label("has_profile_analysis"),
            func.coalesce(agg.plans.c.plan_count, 0).label("plan_count"),
            agg.plans.c.difficulty_factor.label("plan_difficulty_factor"),
            func.coalesce(agg.checkins.c.total_checkins, 0).label("total_checkins"),
            func.coalesce(agg.checkins.c.checkins_30d, 0).label("checkins_30d"),
            agg.checkins.c.last_checkin_date.label("last_checkin_date"),
            func.coalesce(agg.analyses.c.analysis_count, 0).label("analysis_count"),
            agg.last_active.label("last_active_at"),
        )
        .select_from(User)
        .outerjoin(agg.plans, agg.plans.c.user_id == User.id)
        .outerjoin(agg.checkins, agg.checkins.c.user_id == User.id)
        .outerjoin(agg.analyses, agg.analyses.c.user_id == User.id)
        .outerjoin(agg.weights, agg.weights.c.user_id == User.id)
        .outerjoin(agg.chats, agg.chats.c.user_id == User.id)
    )


def _flag_predicates(agg: _Aggregates, now: dt.datetime) -> dict[str, ColumnElement[Any]]:
    """SQL predicates mirroring the Python flag rules (same constants, same thresholds)."""
    today = now.date()
    plan_count = func.coalesce(agg.plans.c.plan_count, 0)
    analysis_count = func.coalesce(agg.analyses.c.analysis_count, 0)
    last_checkin = agg.checkins.c.last_checkin_date

    return {
        FLAG_NEW_NO_PLAN: and_(
            User.created_at <= now - dt.timedelta(days=NEW_NO_PLAN_DAYS),
            plan_count == 0,
        ),
        FLAG_PLANNED_NO_CHECKIN: and_(
            plan_count > 0,
            or_(
                last_checkin.is_(None),
                last_checkin <= today - dt.timedelta(days=PLANNED_NO_CHECKIN_DAYS),
            ),
        ),
        FLAG_INACTIVE_14D: agg.last_active <= now - dt.timedelta(days=INACTIVE_DAYS),
        FLAG_NEVER_ANALYZED: and_(
            User.created_at <= now - dt.timedelta(days=NEVER_ANALYZED_DAYS),
            User.body_analysis.is_(None),
            analysis_count == 0,
        ),
        FLAG_API_KEY_MISSING: _no_api_key_expression(),
    }


def _search_conditions(term: str) -> tuple[ColumnElement[Any], int | None]:
    """Fuzzy search over nickname/email/openid plus exact numeric user id."""
    pattern = f"%{_escape_like(term)}%"
    clauses: list[ColumnElement[Any]] = [
        User.nickname.ilike(pattern, escape=_LIKE_ESCAPE),
        User.email.ilike(pattern, escape=_LIKE_ESCAPE),
        User.openid.ilike(pattern, escape=_LIKE_ESCAPE),
    ]
    numeric = _numeric_id(term)
    if numeric is not None:
        clauses.append(User.id == numeric)
    return or_(*clauses), numeric


def _conditions(
    agg: _Aggregates,
    now: dt.datetime,
    *,
    q: str | None,
    has_plan: bool | None,
    registered_from: dt.datetime | None,
    registered_to: dt.datetime | None,
    checkins_min: int | None,
    checkins_max: int | None,
    active_within_days: int | None,
    is_admin: bool | None,
    has_api_key: bool | None,
    flags: Sequence[str] | None,
) -> tuple[list[ColumnElement[Any]], int | None]:
    """Combine request filters with AND; the returned int is the numeric search term."""
    conditions: list[ColumnElement[Any]] = []
    numeric_id: int | None = None

    if q and q.strip():
        search_clause, numeric_id = _search_conditions(q.strip())
        conditions.append(search_clause)

    plan_count = func.coalesce(agg.plans.c.plan_count, 0)
    total_checkins = func.coalesce(agg.checkins.c.total_checkins, 0)

    if has_plan is not None:
        conditions.append(plan_count > 0 if has_plan else plan_count == 0)
    if registered_from is not None:
        conditions.append(User.created_at >= _as_utc(registered_from))
    if registered_to is not None:
        conditions.append(User.created_at < _as_utc(registered_to))
    if checkins_min is not None:
        conditions.append(total_checkins >= checkins_min)
    if checkins_max is not None:
        conditions.append(total_checkins <= checkins_max)
    if active_within_days is not None:
        conditions.append(
            agg.last_active >= now - dt.timedelta(days=active_within_days)
        )
    if is_admin is not None:
        conditions.append(User.is_admin.is_(is_admin))
    if has_api_key is not None:
        conditions.append(_has_api_key_expression() if has_api_key else _no_api_key_expression())
    if flags:
        flag_predicates = _flag_predicates(agg, now)
        selected = [flag_predicates[flag] for flag in flags if flag in flag_predicates]
        if selected:
            conditions.append(or_(*selected))

    return conditions, numeric_id


def _no_api_key_expression() -> ColumnElement[Any]:
    """Whether a user has no own provider key configured."""
    return or_(User.llm_api_key.is_(None), User.llm_api_key == "")


def _order_by(agg: _Aggregates, sort: str, numeric_id: int | None) -> list[Any]:
    """Fixed-enum sort clauses; a numeric search term ranks its exact id match first."""
    clauses: list[Any] = []
    if numeric_id is not None:
        clauses.append(case((User.id == numeric_id, 0), else_=1))

    if sort == SORT_REGISTERED_ASC:
        clauses.extend([User.created_at.asc(), User.id.asc()])
    elif sort == SORT_LAST_ACTIVE_ASC:
        clauses.extend([agg.last_active.asc(), User.id.asc()])
    elif sort == SORT_LAST_ACTIVE_DESC:
        clauses.extend([agg.last_active.desc(), User.id.desc()])
    else:  # SORT_REGISTERED_DESC is the default
        clauses.extend([User.created_at.desc(), User.id.desc()])
    return clauses


def _python_flags(
    *,
    created_at: dt.datetime,
    plan_count: int,
    last_checkin_date: dt.date | None,
    last_active_at: dt.datetime,
    has_body_analysis: bool,
    has_api_key: bool,
    now: dt.datetime,
) -> list[str]:
    """Derive attention flags for one returned row, in the fixed ALL_FLAGS order."""
    today = now.date()
    flags: set[str] = set()

    if created_at <= now - dt.timedelta(days=NEW_NO_PLAN_DAYS) and plan_count == 0:
        flags.add(FLAG_NEW_NO_PLAN)
    if plan_count > 0 and (
        last_checkin_date is None
        or last_checkin_date <= today - dt.timedelta(days=PLANNED_NO_CHECKIN_DAYS)
    ):
        flags.add(FLAG_PLANNED_NO_CHECKIN)
    if last_active_at <= now - dt.timedelta(days=INACTIVE_DAYS):
        flags.add(FLAG_INACTIVE_14D)
    if created_at <= now - dt.timedelta(days=NEVER_ANALYZED_DAYS) and not has_body_analysis:
        flags.add(FLAG_NEVER_ANALYZED)
    if not has_api_key:
        flags.add(FLAG_API_KEY_MISSING)

    return [flag for flag in ALL_FLAGS if flag in flags]


def _serialize_row(row: Any, now: dt.datetime) -> dict[str, Any]:
    """Shape one aggregated row into the API contract (masking happens here)."""
    created_at = _as_utc(row.created_at)
    last_active_at = _as_utc(row.last_active_at)
    assert created_at is not None and last_active_at is not None  # users.created_at is NOT NULL

    last_checkin_date = row.last_checkin_date
    days_since_last_checkin = (
        (now.date() - last_checkin_date).days if last_checkin_date is not None else None
    )
    plan_count = int(row.plan_count or 0)
    analysis_count = int(row.analysis_count or 0)
    has_body_analysis = bool(row.has_profile_analysis) or analysis_count > 0
    has_api_key = bool(row.has_api_key)

    return {
        "id": row.id,
        "nickname": row.nickname,
        "avatar_url": row.avatar_url,
        "openid": mask_openid(row.openid),
        "email_masked": mask_email(row.email),
        "is_admin": bool(row.is_admin),
        "has_api_key": has_api_key,
        "llm_provider": row.llm_provider if has_api_key else None,
        "created_at": created_at,
        "has_plan": plan_count > 0,
        "plan_difficulty_factor": (
            float(row.plan_difficulty_factor) if row.plan_difficulty_factor is not None else None
        ),
        "total_checkins": int(row.total_checkins or 0),
        "checkins_30d": int(row.checkins_30d or 0),
        "last_checkin_date": last_checkin_date,
        "last_active_at": last_active_at,
        "days_since_last_checkin": days_since_last_checkin,
        "flags": _python_flags(
            created_at=created_at,
            plan_count=plan_count,
            last_checkin_date=last_checkin_date,
            last_active_at=last_active_at,
            has_body_analysis=has_body_analysis,
            has_api_key=has_api_key,
            now=now,
        ),
    }


async def list_users(
    db: AsyncSession,
    *,
    q: str | None = None,
    has_plan: bool | None = None,
    registered_from: dt.datetime | None = None,
    registered_to: dt.datetime | None = None,
    checkins_min: int | None = None,
    checkins_max: int | None = None,
    active_within_days: int | None = None,
    is_admin: bool | None = None,
    has_api_key: bool | None = None,
    flags: Sequence[str] | None = None,
    sort: str = SORT_REGISTERED_DESC,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Return one page of the admin user directory plus the filtered total."""
    now = utc_now()
    aggregates = _build_aggregates(now)
    base_query = _base_select(aggregates)
    conditions, numeric_id = _conditions(
        aggregates,
        now,
        q=q,
        has_plan=has_plan,
        registered_from=registered_from,
        registered_to=registered_to,
        checkins_min=checkins_min,
        checkins_max=checkins_max,
        active_within_days=active_within_days,
        is_admin=is_admin,
        has_api_key=has_api_key,
        flags=flags,
    )

    count_query = select(func.count()).select_from(
        base_query.with_only_columns(User.id, maintain_column_froms=True)
        .where(*conditions)
        .subquery()
    )
    total = (await db.execute(count_query)).scalar() or 0

    page_query = (
        base_query.where(*conditions)
        .order_by(*_order_by(aggregates, sort, numeric_id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(page_query)).mappings().all()

    return [_serialize_row(row, now) for row in rows], int(total)
