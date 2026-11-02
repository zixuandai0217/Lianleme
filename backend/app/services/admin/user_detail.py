"""管理后台用户详情聚合（工单 37）：把单用户的一屏视图按分区组装出来。

复用的是既有口径，不在这里重造规则：

- **档案与需关注标记**：``user_directory.load_user_row``（与列表同一组聚合子查询、
  同一套阈值、同一套掩码），所以列表说「有计划没打卡」、详情不会给出别的结论；
- **计划与最近一次调整**：``PlanService.get_current_plan_with_explanation``（工单 20
  的解释投影：生成依据 + 最近一次调整结论），详情不自己读调整表拼理由；
- **连续天数与累计打卡**：``WorkoutService.get_stats``（用户自己的统计接口同源）；
- **行为轨迹**：由既有记录的 ``created_at`` 派生，不引入埋点。当前模型没有登录会话表，
  所以「最近登录」无法精确得到，轨迹里只有业务事件时间。

性能取舍：详情是**单用户**请求，按分区各发固定的几条查询；**未请求的分区不发查询**。
列表接口那种「一次聚合查询集」是批量场景的约束，不是这里的约束。

空值语义：缺计划 / 缺体型分析时对应分区为 null；``checkins`` / ``weights`` /
``timeline`` / ``usage`` 恒为对象（内容可能为空），只有未知用户 ID 才是 404。
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.local_time import local_date
from app.models.adjustment import PlanAdjustment
from app.models.body_analysis import BodyAnalysisRecord
from app.models.chat_message import ChatMessageRecord
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord
from app.schemas.admin import ADMIN_TIMELINE_EVENT_TYPES
from app.services.admin import user_directory
from app.services.admin.user_directory import as_utc
from app.services.plan.plan_service import PlanService
from app.services.workout.workout_service import WorkoutService

# 序列窗口：含今天在内的 90 个自然日。窗口外的记录既不进序列、也不进完成率分布。
WINDOW_DAYS = 90

# 完成率分布的三档（与产品文案一致，顺序即响应里 dict 的插入顺序）。
RATE_BUCKETS: tuple[str, ...] = ("0-49", "50-79", "80-100")

# 同一时刻多条事件时的固定次序（先按时间倒序、再按枚举顺序），保证分页结果稳定。
_TIMELINE_RANK = {event_type: index for index, event_type in enumerate(ADMIN_TIMELINE_EVENT_TYPES)}

# 调整方向的运营文案（方向本身由 AdjustGraph 写入，越界值原样展示以免丢信息）。
_DIRECTION_LABELS = {"increase": "上调难度", "decrease": "下调难度", "keep": "维持难度"}


def _text(value: object) -> str | None:
    """把快照里的自由值收敛成可读文本；非预期类型返回 None 而不是让读取失败。"""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _text_list(value: object) -> list[str] | None:
    """列表字段的正常形态是 ``list[str]``；偶发写成单个字符串时按单元素兜底。"""
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else None
    if isinstance(value, (list, tuple)):
        items = [item for item in (_text(entry) for entry in value) if item]
        return items or None
    return None


def today() -> dt.date:
    """90 天窗口使用的「今天」。

    走共享的本地日期工具（``app.core.local_time``），不再直接用服务器瞬时日期：
    运营在凌晨查看时，详情页的窗口边界必须和用户自己的「今天」一致。
    """
    return local_date()


def window_start(today_value: dt.date) -> dt.date:
    """The first date inside the 90-day window (the window includes today)."""
    return today_value - dt.timedelta(days=WINDOW_DAYS - 1)


def _rate_bucket(rate: float) -> str:
    """Completion rate -> fixed distribution bucket (0-1 scale)."""
    if rate >= 0.8:
        return "80-100"
    if rate >= 0.5:
        return "50-79"
    return "0-49"


def _analysis_summary(
    result: Any, analyzed_at: dt.datetime | None, source: str
) -> dict[str, Any] | None:
    """Project one stored analysis JSON into the detail summary (never echoes raw input)."""
    if not isinstance(result, dict) or not result:
        return None
    summary = {
        "body_type": _text(result.get("body_type")),
        "body_fat_range": _text(result.get("body_fat_range")),
        "weak_muscles": _text_list(result.get("weak_muscles")),
        "strengths": _text_list(result.get("strengths")),
        "summary": _text(result.get("summary")),
        "analyzed_at": analyzed_at,
        "source": source,
    }
    return None if all(value is None for value in summary.values()) else summary


async def _body_analysis(db: AsyncSession, user_id: int) -> dict[str, Any] | None:
    """Latest analysis record wins; legacy users fall back to the profile snapshot."""
    record = (
        await db.execute(
            select(BodyAnalysisRecord.result, BodyAnalysisRecord.created_at)
            .where(BodyAnalysisRecord.user_id == user_id)
            .order_by(BodyAnalysisRecord.created_at.desc(), BodyAnalysisRecord.id.desc())
            .limit(1)
        )
    ).first()
    if record is not None:
        summary = _analysis_summary(
            record.result, as_utc(record.created_at), "analysis_record"
        )
        if summary is not None:
            return summary

    snapshot = (
        await db.execute(select(User.body_analysis).where(User.id == user_id))
    ).scalar_one_or_none()
    return _analysis_summary(snapshot, None, "profile_snapshot")


def _day_summary(item: Any) -> dict[str, Any]:
    """One planned day as an operations summary (counts, not the full exercise prose)."""
    exercises = item.exercises or []
    return {
        "day": item.day,
        "focus": item.focus,
        "is_rest_day": bool(item.is_rest_day),
        "exercise_count": len(exercises),
        "total_sets": sum(exercise.sets for exercise in exercises),
        "estimated_duration": item.estimated_duration,
    }


async def _plan(db: AsyncSession, user_id: int) -> dict[str, Any] | None:
    """Current active plan + the ticket-20 explanation projection."""
    plan, explanation = await PlanService(db).get_current_plan_with_explanation(user_id)
    if plan is None:
        return None
    return {
        "plan_id": plan.id,
        "week_start": plan.week_start,
        "difficulty_factor": float(plan.difficulty_factor),
        "status": plan.status,
        "week_structure": [_day_summary(item) for item in plan.weekly_plan],
        "generation": explanation.generation,
        "latest_adjustment": explanation.latest_adjustment,
    }


async def _checkins(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """Last-90-day series + streak + rate distribution, reusing the user's own stats."""
    stats = await WorkoutService(db).get_stats(user_id)
    today_value = today()
    cutoff = window_start(today_value)
    rows = (
        await db.execute(
            select(
                WorkoutRecord.workout_date,
                WorkoutRecord.completion_rate,
                WorkoutRecord.duration_minutes,
                WorkoutRecord.difficulty_rating,
            )
            .where(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= cutoff,
                WorkoutRecord.workout_date <= today_value,
            )
            .order_by(WorkoutRecord.workout_date.desc(), WorkoutRecord.id.desc())
        )
    ).all()

    distribution = {bucket: 0 for bucket in RATE_BUCKETS}
    series: list[dict[str, Any]] = []
    for row in rows:
        rate = float(row.completion_rate or 0.0)
        distribution[_rate_bucket(rate)] += 1
        series.append(
            {
                "workout_date": row.workout_date,
                "completion_rate": rate,
                "duration_minutes": int(row.duration_minutes or 0),
                "difficulty_rating": row.difficulty_rating,
            }
        )

    return {
        "window_days": WINDOW_DAYS,
        "series": series,
        "streak_days": stats.streak_days,
        "total_checkins": stats.total_checkins,
        "completion_rate_distribution": distribution,
    }


async def _weights(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """Last-90-day weight series plus how often the user actually records it."""
    today_value = today()
    cutoff = window_start(today_value)
    rows = (
        await db.execute(
            select(WeightRecord.recorded_date, WeightRecord.weight)
            .where(
                WeightRecord.user_id == user_id,
                WeightRecord.recorded_date >= cutoff,
                WeightRecord.recorded_date <= today_value,
            )
            .order_by(WeightRecord.recorded_date.desc(), WeightRecord.id.desc())
        )
    ).all()

    series = [
        {"recorded_date": row.recorded_date, "weight": float(row.weight)} for row in rows
    ]
    latest = series[0] if series else None
    return {
        "window_days": WINDOW_DAYS,
        "series": series,
        "record_count": len(series),
        "records_per_week": round(len(series) / (WINDOW_DAYS / 7), 2),
        "latest_weight": latest["weight"] if latest else None,
        "last_recorded_date": latest["recorded_date"] if latest else None,
    }


async def _first_latest(
    db: AsyncSession,
    model: Any,
    user_id: int,
    extra_columns: Sequence[Any] = (),
) -> tuple[Any, Any]:
    """First and latest rows of one data source by ``(created_at, id)``; either may be None.

    Two small index-friendly queries instead of one aggregate + a re-read: the detail page
    serves a single user, and the summary needs the columns of the boundary rows.
    """
    columns = [model.id, model.created_at, *extra_columns]
    base = select(*columns).where(model.user_id == user_id)
    first = (
        await db.execute(base.order_by(model.created_at.asc(), model.id.asc()).limit(1))
    ).first()
    latest = (
        await db.execute(base.order_by(model.created_at.desc(), model.id.desc()).limit(1))
    ).first()
    return first, latest


def _event(event_type: str, occurred_at: dt.datetime | None, summary: str, message: str):
    """One timeline event dict, or None when the source has no timestamp."""
    stamp = as_utc(occurred_at)
    if stamp is None:
        return None
    return {
        "type": event_type,
        "occurred_at": stamp,
        "summary": summary,
        "message": message,
    }


async def _timeline(
    db: AsyncSession, user_id: int, created_at: dt.datetime, page: int, page_size: int
) -> dict[str, Any]:
    """Fixed-vocabulary events derived from existing rows, newest first, paginated.

    Nothing is fabricated: a data source that never happened contributes no event, and a
    source with exactly one record contributes only its 「first」 event (the same record
    cannot be both the first and the latest occurrence).
    """
    events: list[dict[str, Any]] = []
    registered = _event("registered", created_at, "账号注册", "用户创建账号")
    if registered is not None:
        events.append(registered)

    first_analysis, latest_analysis = await _first_latest(db, BodyAnalysisRecord, user_id)
    if first_analysis is not None:
        events.append(
            _event(
                "first_body_analysis",
                first_analysis.created_at,
                "首次体型分析",
                "完成第一次体型分析",
            )
        )
    if latest_analysis is not None and (
        first_analysis is None or latest_analysis.id != first_analysis.id
    ):
        events.append(
            _event(
                "latest_body_analysis",
                latest_analysis.created_at,
                "最近一次体型分析",
                "更新了体型分析结果",
            )
        )

    first_plan_at = (
        await db.execute(
            select(func.min(TrainingPlan.created_at)).where(TrainingPlan.user_id == user_id)
        )
    ).scalar()
    events.append(
        _event("first_plan_generated", first_plan_at, "首次生成计划", "生成第一份训练计划")
    )

    adjustment = (
        await db.execute(
            select(
                PlanAdjustment.direction,
                PlanAdjustment.reason,
                PlanAdjustment.created_at,
            )
            .where(PlanAdjustment.user_id == user_id)
            .order_by(PlanAdjustment.created_at.desc(), PlanAdjustment.id.desc())
            .limit(1)
        )
    ).first()
    if adjustment is not None:
        direction = _DIRECTION_LABELS.get(adjustment.direction, adjustment.direction)
        events.append(
            _event(
                "latest_plan_adjustment",
                adjustment.created_at,
                f"计划调整（{direction}）",
                adjustment.reason,
            )
        )

    first_checkin, latest_checkin = await _first_latest(
        db, WorkoutRecord, user_id, (WorkoutRecord.workout_date,)
    )
    for prefix, row, summary in (
        ("first", first_checkin, "首次打卡"),
        ("latest", latest_checkin, "最近一次打卡"),
    ):
        if row is None or (
            prefix == "latest" and first_checkin is not None and row.id == first_checkin.id
        ):
            continue
        events.append(
            _event(
                f"{prefix}_checkin",
                row.created_at,
                summary,
                f"训练日期 {row.workout_date.isoformat()}",
            )
        )

    first_weight, latest_weight = await _first_latest(
        db, WeightRecord, user_id, (WeightRecord.recorded_date, WeightRecord.weight)
    )
    for prefix, row, summary in (
        ("first", first_weight, "首次体重记录"),
        ("latest", latest_weight, "最近一次体重记录"),
    ):
        if row is None or (
            prefix == "latest" and first_weight is not None and row.id == first_weight.id
        ):
            continue
        events.append(
            _event(
                f"{prefix}_weight_record",
                row.created_at,
                summary,
                f"{float(row.weight):g} kg（{row.recorded_date.isoformat()}）",
            )
        )

    latest_chat_at = (
        await db.execute(
            select(func.max(ChatMessageRecord.created_at)).where(
                ChatMessageRecord.user_id == user_id
            )
        )
    ).scalar()
    events.append(
        _event("latest_chat", latest_chat_at, "最近一次对话", "与 AI 教练有对话记录")
    )

    ordered = [event for event in events if event is not None]
    # Stable sort: first by the fixed enum rank, then by time descending; equal timestamps
    # therefore keep a deterministic order across pages.
    ordered.sort(key=lambda event: _TIMELINE_RANK.get(event["type"], len(_TIMELINE_RANK)))
    ordered.sort(key=lambda event: event["occurred_at"], reverse=True)

    total = len(ordered)
    start = (page - 1) * page_size
    return {
        "items": ordered[start : start + page_size] if start < total else [],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _usage(db: AsyncSession, user_id: int, profile: dict[str, Any]) -> dict[str, Any]:
    """AI key state (from the masked directory row) + aggregate chat counts."""
    rows = (
        await db.execute(
            select(
                ChatMessageRecord.role,
                func.count().label("message_count"),
                func.max(ChatMessageRecord.created_at).label("last_message_at"),
            )
            .where(ChatMessageRecord.user_id == user_id)
            .group_by(ChatMessageRecord.role)
        )
    ).all()

    by_role = {row.role: int(row.message_count or 0) for row in rows}
    last_chat_at: dt.datetime | None = None
    for row in rows:
        stamp = as_utc(row.last_message_at)
        if stamp is not None and (last_chat_at is None or stamp > last_chat_at):
            last_chat_at = stamp

    return {
        "has_api_key": bool(profile["has_api_key"]),
        "llm_provider": profile["llm_provider"],
        "chat_message_count": sum(by_role.values()),
        "user_message_count": by_role.get("user", 0),
        "assistant_message_count": by_role.get("assistant", 0),
        "last_chat_at": last_chat_at,
    }


async def get_user_detail(
    db: AsyncSession,
    user_id: int,
    *,
    sections: Iterable[str],
    timeline_page: int = 1,
    timeline_page_size: int = 20,
) -> dict[str, Any] | None:
    """Assemble the requested detail sections for one user; ``None`` means unknown user.

    Only requested sections run their queries: a caller asking for ``profile`` does not
    pay for the timeline, and a slow/empty data source cannot fail the other sections.
    """
    now = user_directory.utc_now()
    profile = await user_directory.load_user_row(db, user_id, now=now)
    if profile is None:
        return None

    requested = tuple(sections)
    payload: dict[str, Any] = {"user_id": user_id, "sections": list(requested)}

    for section in requested:
        if section == "profile":
            payload["profile"] = profile
        elif section == "body_analysis":
            payload["body_analysis"] = await _body_analysis(db, user_id)
        elif section == "plan":
            payload["plan"] = await _plan(db, user_id)
        elif section == "checkins":
            payload["checkins"] = await _checkins(db, user_id)
        elif section == "weights":
            payload["weights"] = await _weights(db, user_id)
        elif section == "timeline":
            payload["timeline"] = await _timeline(
                db, user_id, profile["created_at"], timeline_page, timeline_page_size
            )
        elif section == "usage":
            payload["usage"] = await _usage(db, user_id, profile)

    return payload
