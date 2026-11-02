"""姿态聚合的持久化与只读摘要（工单 43）。

隐私边界在这里收口：会话结束后只把**数值聚合**落库——周期计数、平均质量分、
问题类型直方图、模型调用次数与起止时间。关键点、坐标、帧、角度序列与单次动作
明细一律不进入数据库、不进入响应、不进入日志。

三件事由本模块保证：
- 幂等：``session_id`` 唯一，重复结束返回同一行，不产生第二次写入；
- 所有权：读/删都按当前登录用户过滤，他人聚合 403 且不泄露内容；
- 只读摘要：伤病风险输入只有数值与问题类型计数，没有单次动作明细。
"""

from __future__ import annotations

import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.local_time import local_date
from app.models.pose_aggregate import PoseQualityAggregate
from app.schemas.pose import (
    PoseAggregateListResponse,
    PoseAggregateResponse,
    PoseInjuryIssueCount,
    PoseInjurySummaryResponse,
)
from app.services.pose.evaluation import SCORE_DECIMALS
from app.services.pose.session_store import SessionSummary

# 列表有界：聚合是「最近训练」入口，不做全量导出。
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50
# 伤病摘要默认两周，最长三个月；天数由路由层 Query 约束。
DEFAULT_INJURY_SUMMARY_DAYS = 14
MAX_INJURY_SUMMARY_DAYS = 90
# top-N 问题类型：只给最常见的几类，避免摘要退化成问题清单。
TOP_ISSUES_LIMIT = 5
RATIO_DECIMALS = 3


class PoseAggregateError(Exception):
    """聚合资源的可读错误；由路由层映射成稳定错误码与 HTTP 状态码。"""

    code = "pose_aggregate_error"
    status_code = 400
    message = "姿态聚合操作失败"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.detail = message or self.message


class PoseAggregateNotFound(PoseAggregateError):
    code = "pose_aggregate_not_found"
    status_code = 404
    message = "姿态聚合记录不存在"


class PoseAggregateForbidden(PoseAggregateError):
    code = "pose_aggregate_forbidden"
    status_code = 403
    message = "无权访问其他用户的姿态聚合记录"


def not_evaluable_ratio(not_evaluable_cycles: int, cycles_count: int) -> float:
    """不可评估周期占比；没有周期时返回 0.0，不编造分母。"""
    if cycles_count <= 0:
        return 0.0
    return round(not_evaluable_cycles / cycles_count, RATIO_DECIMALS)


def _aggregate_response(row: PoseQualityAggregate) -> PoseAggregateResponse:
    return PoseAggregateResponse(
        id=row.id,
        session_id=row.session_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        cycles_count=row.cycles_count,
        evaluable_cycles=row.evaluable_cycles,
        not_evaluable_cycles=row.not_evaluable_cycles,
        avg_quality=row.avg_quality,
        issues_histogram=dict(row.issues_histogram or {}),
        model_calls=row.model_calls,
        not_evaluable_ratio=not_evaluable_ratio(
            row.not_evaluable_cycles, row.cycles_count
        ),
        created_at=row.created_at,
    )


async def persist_session_aggregate(
    db: AsyncSession,
    *,
    user_id: int,
    summary: SessionSummary,
    started_at: datetime.datetime,
    finished_at: datetime.datetime,
) -> PoseQualityAggregate:
    """结束会话时写入唯一聚合行；已存在则直接复用，绝不重复写。"""
    existing = await _find_by_session_id(db, summary.session_id)
    if existing is not None:
        return existing

    row = PoseQualityAggregate(
        user_id=user_id,
        session_id=summary.session_id,
        started_at=started_at,
        finished_at=finished_at,
        cycles_count=summary.cycles_count,
        evaluable_cycles=summary.evaluable_cycles,
        not_evaluable_cycles=summary.not_evaluable_cycles,
        avg_quality=summary.avg_quality,
        issues_histogram=dict(sorted(summary.issues_histogram.items())),
        model_calls=summary.model_calls,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        # 并发重复结束：唯一约束兜底，回滚后读回已存在的那一行。
        await db.rollback()
        existing = await _find_by_session_id(db, summary.session_id)
        if existing is None:
            raise
        return existing
    return row


async def _find_by_session_id(
    db: AsyncSession, session_id: str
) -> PoseQualityAggregate | None:
    result = await db.execute(
        select(PoseQualityAggregate).where(
            PoseQualityAggregate.session_id == session_id
        )
    )
    return result.scalars().first()


async def list_aggregates(
    db: AsyncSession, *, user_id: int, limit: int = DEFAULT_LIST_LIMIT
) -> PoseAggregateListResponse:
    """当前用户最近的聚合（按结束时间倒序，有界）。"""
    bounded = max(1, min(limit, MAX_LIST_LIMIT))
    rows = (
        (
            await db.execute(
                select(PoseQualityAggregate)
                .where(PoseQualityAggregate.user_id == user_id)
                .order_by(
                    PoseQualityAggregate.finished_at.desc(),
                    PoseQualityAggregate.id.desc(),
                )
                .limit(bounded)
            )
        )
        .scalars()
        .all()
    )
    total = (
        await db.execute(
            select(func.count(PoseQualityAggregate.id)).where(
                PoseQualityAggregate.user_id == user_id
            )
        )
    ).scalar() or 0
    return PoseAggregateListResponse(
        items=[_aggregate_response(row) for row in rows],
        total=int(total),
    )


async def get_aggregate(
    db: AsyncSession, aggregate_id: int, *, user_id: int
) -> PoseAggregateResponse:
    """读取自己的聚合详情；他人 403（不返回内容），不存在 404。"""
    row = await db.get(PoseQualityAggregate, aggregate_id)
    if row is None:
        raise PoseAggregateNotFound()
    if row.user_id != user_id:
        raise PoseAggregateForbidden()
    return _aggregate_response(row)


async def delete_aggregate(
    db: AsyncSession, aggregate_id: int, *, user_id: int
) -> str:
    """硬删除自己的聚合，返回被删聚合的会话标识（用于同步丢弃会话内存）。"""
    row = await db.get(PoseQualityAggregate, aggregate_id)
    if row is None:
        raise PoseAggregateNotFound()
    if row.user_id != user_id:
        raise PoseAggregateForbidden()
    session_id = row.session_id
    await db.delete(row)
    await db.flush()
    return session_id


async def build_injury_summary(
    db: AsyncSession, *, user_id: int, days: int = DEFAULT_INJURY_SUMMARY_DAYS
) -> PoseInjurySummaryResponse:
    """近 N 天的只读数值摘要：平均分、top-N 问题类型、覆盖训练次数与不可评估占比。"""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    rows = (
        (
            await db.execute(
                select(PoseQualityAggregate)
                .where(
                    PoseQualityAggregate.user_id == user_id,
                    PoseQualityAggregate.finished_at >= cutoff,
                )
                .order_by(PoseQualityAggregate.finished_at.desc())
            )
        )
        .scalars()
        .all()
    )

    sessions_covered = len(rows)
    cycles_covered = sum(row.cycles_count for row in rows)
    evaluable_cycles = sum(row.evaluable_cycles for row in rows)
    not_evaluable_cycles = sum(row.not_evaluable_cycles for row in rows)

    # 平均分按可评估周期加权：会话长短不同，不能把会话平均分再简单平均。
    weighted_total = sum(row.avg_quality * row.evaluable_cycles for row in rows)
    avg_quality = (
        round(weighted_total / evaluable_cycles, SCORE_DECIMALS)
        if evaluable_cycles > 0
        else 0.0
    )

    histogram: dict[str, int] = {}
    for row in rows:
        for issue_type, count in (row.issues_histogram or {}).items():
            histogram[issue_type] = histogram.get(issue_type, 0) + int(count)
    top_issues = [
        PoseInjuryIssueCount(type=issue_type, count=count)
        for issue_type, count in sorted(
            histogram.items(), key=lambda pair: (-pair[1], pair[0])
        )[:TOP_ISSUES_LIMIT]
    ]

    return PoseInjurySummaryResponse(
        window_days=days,
        sessions_covered=sessions_covered,
        training_days=len({local_date(row.finished_at) for row in rows}),
        cycles_covered=cycles_covered,
        evaluable_cycles=evaluable_cycles,
        not_evaluable_cycles=not_evaluable_cycles,
        not_evaluable_ratio=not_evaluable_ratio(not_evaluable_cycles, cycles_covered),
        avg_quality=avg_quality,
        quality_available=evaluable_cycles > 0,
        top_issues=top_issues,
    )
