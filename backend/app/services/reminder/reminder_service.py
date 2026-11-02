"""提醒调度服务：一次 tick 只做「规则判定 + 投递记录写入」。

边界（与任务持久化 spec 的分工）：tick 内不发生任何外部网络调用（LLM、对象存储、
推送服务），也不 spawn 协程去跑重活；需要异步重活时由后续工单投递持久作业。
tick 的幂等由 ``reminder_deliveries`` 的唯一键兜底：重复 tick 只会命中同一条记录。

工单 34 起，判定结果分三种落库形态：
- ``sent``：真正要发给用户的通知；
- ``skipped``：命中了规则但被免打扰、每日上限、本周已发等原因裁掉，留给运营排查；
- 顺延（quiet hours 内但当日窗口还开着）不落记录，交给后续 tick 正常投递。
"""
import datetime
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.local_time import to_local
from app.core.logging import (
    EVENT_REMINDER_DELIVERY_FAILED,
    EVENT_REMINDER_TICK_COMPLETED,
    FIELD_DELIVERED,
    FIELD_DUPLICATES,
    FIELD_ERROR_CLASS,
    FIELD_EVALUATED_USERS,
    FIELD_FAILED,
    FIELD_RULE_CODE,
    FIELD_SKIPPED,
    FIELD_USER_ID,
    log_event,
)
from app.models.body_analysis import BodyAnalysisRecord
from app.models.plan import TrainingPlan
from app.models.push import PushSubscription
from app.models.record import WorkoutRecord
from app.models.reminder import (
    CHANNEL_IN_APP,
    DELIVERY_STATUS_SENT,
    DELIVERY_STATUS_SKIPPED,
    ReminderDelivery,
)
from app.models.reminder_preference import ReminderPreference
from app.models.user import User
from app.schemas.plan import TrainingPlanSchema
from app.services.notification.push_service import enqueue_web_push_delivery
from app.services.plan.plan_service import PlanService
from app.services.reminder import preferences as preference_service
from app.services.reminder.rules import (
    RULE_ONBOARDING_NUDGE,
    SKIP_DAILY_CAP,
    SKIP_DISABLED,
    SKIP_QUIET_HOURS,
    ReminderCandidate,
    ReminderContext,
    ReminderPreferences,
    daily_window,
    evaluate_rules,
    in_quiet_hours,
    parse_hhmm,
    week_start_of,
)

logger = logging.getLogger(__name__)


@dataclass
class TickSummary:
    """一次 tick 的可观察摘要（运维与测试都读它）。"""

    evaluated_users: int = 0
    delivered: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0
    status: str = "ok"


@dataclass
class DeliveryResult:
    """单条投递的结果分类，用于摘要与排查。"""

    outcome: str  # delivered / skipped / duplicate / failed
    notification_id: int | None = None


class ReminderService:
    """提醒规则的判定与投递记录写入（站内通道即收件箱）。"""

    def __init__(self, db: AsyncSession, reminder_hour: int | None = None):
        self.db = db
        self.reminder_hour = settings.REMINDER_HOUR if reminder_hour is None else reminder_hour

    # ---------- tick ----------
    async def tick(self, now_local: datetime.datetime) -> TickSummary:
        """对全部用户跑一遍六条规则；返回本次判定与投递摘要。

        固定数量的批量读查询（用户、计划、打卡、分析、偏好、近期投递）一次取齐，
        再在内存里逐用户判定：tick 每 60 秒跑一次，逐用户查询会让成本随用户数线性增长。
        """
        summary = TickSummary()
        users = (await self.db.execute(select(User))).scalars().all()
        summary.evaluated_users = len(users)
        if not users:
            return summary

        today = now_local.date()
        week_start = week_start_of(today)
        facts = await self._load_facts(today, week_start)
        reminder_hour = self.reminder_hour

        for user in users:
            prefs_row = facts.preferences.get(user.id)
            prefs = (
                preference_service.to_rules_preferences(prefs_row)
                if prefs_row is not None
                else ReminderPreferences()
            )
            plan = facts.plans.get(user.id)
            workout = (
                PlanService._workout_for_weekday(plan, now_local.isoweekday())
                if plan
                else None
            )

            context = ReminderContext(
                now_local=now_local,
                is_training_day=workout is not None and not workout.is_rest_day,
                has_checked_in_today=user.id in facts.checked_in_today,
                focus=workout.focus if workout else None,
                estimated_duration=workout.estimated_duration if workout else None,
                last_checkin_date=facts.last_checkin.get(user.id),
                week_checkins=facts.week_checkins.get(user.id, 0),
                has_plan=plan is not None,
                has_body_analysis=(
                    user.body_analysis is not None or user.id in facts.analysis_users
                ),
                registered_days_ago=self._days_since(user.created_at, today),
                onboarding_nudges_sent=facts.onboarding_sent.get(user.id, 0),
                reminders_sent_today=facts.sent_today.get(user.id, 0),
                rules_sent_this_week=facts.rules_this_week.get(user.id, frozenset()),
                reminder_hour=reminder_hour,
            )

            outcomes = evaluate_rules(context, prefs)
            candidates = sorted(
                (outcome.candidate for outcome in outcomes if outcome.candidate),
                key=lambda candidate: candidate.priority,
            )
            skip_reasons = {
                outcome.rule_code: outcome.skip_reason
                for outcome in outcomes
                if outcome.skip_reason and outcome.skip_reason != SKIP_DISABLED
            }

            candidates, skip_reasons = self._apply_quiet_hours(
                now_local, prefs, candidates, skip_reasons
            )
            candidates, skip_reasons = self._apply_daily_cap(
                facts.sent_today.get(user.id, 0), prefs, candidates, skip_reasons
            )

            for candidate in candidates:
                result = await self._record_delivery(user.id, candidate, today)
                self._count(summary, result)
                if result.outcome == "delivered":
                    # 重通道只在站内记录真正写入后追加：tick 只落记录与作业，
                    # 真正的网络发送由 PushJobExecutor 负责（tick 内零外部调用）。
                    subscription_id = facts.push_subscriptions.get(user.id)
                    if subscription_id is not None:
                        await enqueue_web_push_delivery(
                            self.db,
                            user_id=user.id,
                            rule_code=candidate.rule_code,
                            local_date=today,
                            subscription_id=subscription_id,
                            payload=self._delivery_payload(candidate),
                        )
            for rule_code, reason in skip_reasons.items():
                result = await self._record_skip(user.id, rule_code, today, reason)
                self._count(summary, result)

        log_event(
            logger,
            EVENT_REMINDER_TICK_COMPLETED,
            message="提醒 tick 完成",
            **{
                FIELD_EVALUATED_USERS: summary.evaluated_users,
                FIELD_DELIVERED: summary.delivered,
                FIELD_DUPLICATES: summary.duplicates,
                FIELD_SKIPPED: summary.skipped,
                FIELD_FAILED: summary.failed,
            },
        )
        return summary

    # ---------- tick helpers ----------
    def _apply_quiet_hours(
        self,
        now_local: datetime.datetime,
        prefs: ReminderPreferences,
        candidates: list[ReminderCandidate],
        skip_reasons: dict[str, str],
    ) -> tuple[list[ReminderCandidate], dict[str, str]]:
        """Defer candidates inside quiet hours, or mark them skipped when the window closed."""
        if not candidates or not in_quiet_hours(prefs, now_local.time()):
            return candidates, skip_reasons

        quiet_end = parse_hhmm(prefs.quiet_hours_end)
        quiet_end_dt = now_local.replace(
            hour=quiet_end.hour, minute=quiet_end.minute, second=0, microsecond=0
        )
        if quiet_end_dt <= now_local:
            quiet_end_dt += datetime.timedelta(days=1)
        _, window_end = daily_window(now_local, self.reminder_hour)

        if quiet_end_dt < window_end:
            # 当日窗口还开着：本轮不发也不记，等到免打扰结束后的 tick 再正常投递。
            return [], skip_reasons

        reasons = dict(skip_reasons)
        for candidate in candidates:
            reasons[candidate.rule_code] = SKIP_QUIET_HOURS
        return [], reasons

    def _apply_daily_cap(
        self,
        sent_today: int,
        prefs: ReminderPreferences,
        candidates: list[ReminderCandidate],
        skip_reasons: dict[str, str],
    ) -> tuple[list[ReminderCandidate], dict[str, str]]:
        """Keep the highest-priority candidates under the daily cap; record the rest."""
        if not candidates:
            return candidates, skip_reasons
        remaining = max(0, prefs.daily_cap - sent_today)
        chosen = candidates[:remaining]
        reasons = dict(skip_reasons)
        for candidate in candidates[remaining:]:
            reasons[candidate.rule_code] = SKIP_DAILY_CAP
        return chosen, reasons

    @staticmethod
    def _count(summary: TickSummary, result: DeliveryResult) -> None:
        if result.outcome == "delivered":
            summary.delivered += 1
        elif result.outcome == "skipped":
            summary.skipped += 1
        elif result.outcome == "duplicate":
            summary.duplicates += 1
        else:
            summary.failed += 1

    @staticmethod
    def _days_since(created_at: datetime.datetime | None, today: datetime.date) -> int:
        """Registration age in *local* days (naive timestamps are interpreted as UTC)."""
        if created_at is None:
            return 0
        return max(0, (today - to_local(created_at).date()).days)

    async def _load_facts(self, today: datetime.date, week_start: datetime.date) -> "_Facts":
        """All reads needed by one tick, in a fixed number of queries."""
        since = week_start

        last_checkin_rows = (
            await self.db.execute(
                select(WorkoutRecord.user_id, func.max(WorkoutRecord.workout_date)).group_by(
                    WorkoutRecord.user_id
                )
            )
        ).all()
        week_rows = (
            await self.db.execute(
                select(WorkoutRecord.user_id, func.count())
                .where(WorkoutRecord.workout_date >= week_start)
                .group_by(WorkoutRecord.user_id)
            )
        ).all()
        analysis_users = set(
            (
                await self.db.execute(select(BodyAnalysisRecord.user_id).distinct())
            ).scalars().all()
        )
        prefs_rows = (await self.db.execute(select(ReminderPreference))).scalars().all()
        delivery_rows = (
            await self.db.execute(
                select(
                    ReminderDelivery.user_id,
                    ReminderDelivery.rule_code,
                    ReminderDelivery.local_date,
                ).where(
                    ReminderDelivery.channel == CHANNEL_IN_APP,
                    ReminderDelivery.status == DELIVERY_STATUS_SENT,
                    ReminderDelivery.local_date >= since,
                )
            )
        ).all()
        onboarding_rows = (
            await self.db.execute(
                select(ReminderDelivery.user_id, func.count())
                .where(
                    ReminderDelivery.channel == CHANNEL_IN_APP,
                    ReminderDelivery.status == DELIVERY_STATUS_SENT,
                    ReminderDelivery.rule_code == RULE_ONBOARDING_NUDGE,
                )
                .group_by(ReminderDelivery.user_id)
            )
        ).all()

        rules_this_week: dict[int, set[str]] = {}
        sent_today: dict[int, int] = {}
        for user_id, rule_code, local_date in delivery_rows:
            rules_this_week.setdefault(user_id, set()).add(rule_code)
            if local_date == today:
                sent_today[user_id] = sent_today.get(user_id, 0) + 1

        return _Facts(
            plans=await self._active_plans_by_user(),
            checked_in_today=await self._checked_in_users(today),
            last_checkin={user_id: last for user_id, last in last_checkin_rows},
            week_checkins={user_id: count for user_id, count in week_rows},
            analysis_users=analysis_users,
            preferences={row.user_id: row for row in prefs_rows},
            rules_this_week={
                user_id: frozenset(codes) for user_id, codes in rules_this_week.items()
            },
            sent_today=sent_today,
            onboarding_sent={user_id: count for user_id, count in onboarding_rows},
            push_subscriptions=await self._active_push_subscriptions(),
        )

    async def _active_push_subscriptions(self) -> dict[int, int]:
        """每个用户挑一条有效订阅（最新一条），一次查询取齐。

        通道未配置时不查库：未启用推送的环境不承担这份额外读成本。
        """
        if not settings.web_push_available():
            return {}
        rows = (
            await self.db.execute(
                select(PushSubscription.user_id, PushSubscription.id)
                .where(PushSubscription.is_active.is_(True))
                .order_by(
                    PushSubscription.user_id,
                    PushSubscription.created_at.desc(),
                    PushSubscription.id.desc(),
                )
            )
        ).all()
        subscriptions: dict[int, int] = {}
        for user_id, subscription_id in rows:
            subscriptions.setdefault(user_id, subscription_id)
        return subscriptions

    async def _active_plans_by_user(self) -> dict[int, TrainingPlanSchema]:
        """Latest active plan per user, in one query (newest week_start wins)."""
        rows = (
            (
                await self.db.execute(
                    select(TrainingPlan)
                    .where(TrainingPlan.status == "active")
                    .order_by(TrainingPlan.user_id, TrainingPlan.week_start.desc())
                )
            )
            .scalars()
            .all()
        )
        plans: dict[int, TrainingPlanSchema] = {}
        for row in rows:
            plans.setdefault(row.user_id, PlanService._to_schema(row))
        return plans

    async def _checked_in_users(self, local_date: datetime.date) -> set[int]:
        """Users who already checked in on the local date, in one query."""
        rows = (
            await self.db.execute(
                select(WorkoutRecord.user_id)
                .where(WorkoutRecord.workout_date == local_date)
                .distinct()
            )
        ).scalars().all()
        return set(rows)

    # ---------- delivery ----------
    async def _record_delivery(
        self, user_id: int, candidate: ReminderCandidate, local_date: datetime.date
    ) -> DeliveryResult:
        """Persist one delivered notification (the inbox row)."""
        return await self._insert(
            user_id,
            candidate.rule_code,
            local_date,
            status=DELIVERY_STATUS_SENT,
            payload=self._delivery_payload(candidate),
        )

    @staticmethod
    def _delivery_payload(candidate: ReminderCandidate) -> dict:
        """渲染结果的唯一形状：站内收件箱与 web_push 作业共用，避免两处漂移。"""
        return {
            "title": candidate.title,
            "body": candidate.body,
            "target_path": candidate.target_path,
            "params": candidate.params,
        }

    async def _record_skip(
        self, user_id: int, rule_code: str, local_date: datetime.date, reason: str
    ) -> DeliveryResult:
        """Persist one suppressed candidate with the reason ops needs to answer "why not"."""
        return await self._insert(
            user_id,
            rule_code,
            local_date,
            status=DELIVERY_STATUS_SKIPPED,
            payload={"skip_reason": reason},
        )

    async def _insert(
        self,
        user_id: int,
        rule_code: str,
        local_date: datetime.date,
        *,
        status: str,
        payload: dict,
    ) -> DeliveryResult:
        delivery = ReminderDelivery(
            user_id=user_id,
            rule_code=rule_code,
            local_date=local_date,
            channel=CHANNEL_IN_APP,
            status=status,
            payload=payload,
        )
        try:
            # 唯一键冲突只应回滚这一条（SAVEPOINT），不能让整次 tick 的事务一起失效。
            async with self.db.begin_nested():
                self.db.add(delivery)
                await self.db.flush()
        except IntegrityError:
            return DeliveryResult(outcome="duplicate")
        except Exception as exc:  # pragma: no cover - 防御性兜底
            log_event(
                logger,
                EVENT_REMINDER_DELIVERY_FAILED,
                message="提醒投递写入失败",
                level=logging.WARNING,
                **{
                    FIELD_USER_ID: user_id,
                    FIELD_RULE_CODE: rule_code,
                    FIELD_ERROR_CLASS: type(exc).__name__,
                },
            )
            return DeliveryResult(outcome="failed")
        return DeliveryResult(
            outcome="skipped" if status == DELIVERY_STATUS_SKIPPED else "delivered",
            notification_id=delivery.id,
        )

    # ---------- 运营查询 ----------
    async def list_deliveries(
        self,
        *,
        user_id: int | None = None,
        status: str | None = None,
        local_date_from: datetime.date | None = None,
        local_date_to: datetime.date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReminderDelivery], int]:
        """投递记录（含 skipped），供运营回答「为什么这个人今天没收到提醒」。"""
        conditions = [ReminderDelivery.channel == CHANNEL_IN_APP]
        if user_id is not None:
            conditions.append(ReminderDelivery.user_id == user_id)
        if status is not None:
            conditions.append(ReminderDelivery.status == status)
        if local_date_from is not None:
            conditions.append(ReminderDelivery.local_date >= local_date_from)
        if local_date_to is not None:
            conditions.append(ReminderDelivery.local_date <= local_date_to)

        total = (
            await self.db.execute(
                select(func.count()).select_from(ReminderDelivery).where(*conditions)
            )
        ).scalar() or 0
        rows = (
            (
                await self.db.execute(
                    select(ReminderDelivery)
                    .where(*conditions)
                    .order_by(
                        ReminderDelivery.created_at.desc(), ReminderDelivery.id.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    # ---------- 收件箱 ----------
    def _inbox_filter(self, user_id: int):
        return (
            ReminderDelivery.user_id == user_id,
            ReminderDelivery.channel == CHANNEL_IN_APP,
            ReminderDelivery.status == DELIVERY_STATUS_SENT,
        )

    async def unread_count(self, user_id: int) -> int:
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(ReminderDelivery)
                .where(*self._inbox_filter(user_id), ReminderDelivery.read_at.is_(None))
            )
        ).scalar() or 0
        return int(count)

    async def list_notifications(
        self,
        user_id: int,
        *,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReminderDelivery], int, int]:
        """Returns (rows, total, unread_count) for one inbox page."""
        conditions = list(self._inbox_filter(user_id))
        if unread_only:
            conditions.append(ReminderDelivery.read_at.is_(None))

        total = (
            await self.db.execute(
                select(func.count()).select_from(ReminderDelivery).where(*conditions)
            )
        ).scalar() or 0

        rows = (
            (
                await self.db.execute(
                    select(ReminderDelivery)
                    .where(*conditions)
                    .order_by(
                        ReminderDelivery.created_at.desc(), ReminderDelivery.id.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total), await self.unread_count(user_id)

    async def mark_read(
        self, user_id: int, notification_id: int, *, now: datetime.datetime
    ) -> ReminderDelivery | None:
        delivery = await self.db.get(ReminderDelivery, notification_id)
        if delivery is None or delivery.user_id != user_id:
            return None
        if delivery.channel != CHANNEL_IN_APP or delivery.status != DELIVERY_STATUS_SENT:
            return None
        if delivery.read_at is None:
            delivery.read_at = now
            await self.db.flush()
        return delivery

    async def mark_all_read(self, user_id: int, *, now: datetime.datetime) -> int:
        rows = (
            (
                await self.db.execute(
                    select(ReminderDelivery).where(
                        *self._inbox_filter(user_id), ReminderDelivery.read_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.read_at = now
        if rows:
            await self.db.flush()
        return len(rows)


@dataclass
class _Facts:
    """Per-tick bulk facts; one field per batch query."""

    plans: dict[int, TrainingPlanSchema]
    checked_in_today: set[int]
    last_checkin: dict[int, datetime.date]
    week_checkins: dict[int, int]
    analysis_users: set[int]
    preferences: dict[int, ReminderPreference]
    rules_this_week: dict[int, frozenset[str]]
    sent_today: dict[int, int]
    onboarding_sent: dict[int, int]
    push_subscriptions: dict[int, int]
