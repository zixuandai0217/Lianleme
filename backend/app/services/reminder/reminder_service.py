"""提醒调度服务：一次 tick 只做「规则判定 + 投递记录写入」。

边界（与任务持久化 spec 的分工）：tick 内不发生任何外部网络调用（LLM、对象存储、
推送服务），也不 spawn 协程去跑重活；需要异步重活时由后续工单投递持久作业。
tick 的幂等由 ``reminder_deliveries`` 的唯一键兜底：重复 tick 只会命中同一条记录。
"""
import datetime
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import (
    EVENT_REMINDER_DELIVERY_FAILED,
    EVENT_REMINDER_TICK_COMPLETED,
    FIELD_DELIVERED,
    FIELD_DUPLICATES,
    FIELD_ERROR_CLASS,
    FIELD_EVALUATED_USERS,
    FIELD_FAILED,
    FIELD_RULE_CODE,
    FIELD_USER_ID,
    log_event,
)
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.reminder import (
    CHANNEL_IN_APP,
    DELIVERY_STATUS_SENT,
    ReminderDelivery,
)
from app.models.user import User
from app.schemas.plan import TrainingPlanSchema
from app.services.plan.plan_service import PlanService
from app.services.reminder.rules import (
    ReminderCandidate,
    TrainingDayContext,
    evaluate_daily_training,
)

logger = logging.getLogger(__name__)


@dataclass
class TickSummary:
    """一次 tick 的可观察摘要（运维与测试都读它）。"""

    evaluated_users: int = 0
    delivered: int = 0
    duplicates: int = 0
    failed: int = 0
    status: str = "ok"


@dataclass
class DeliveryResult:
    """单条投递的结果分类，用于摘要与排查。"""

    outcome: str  # delivered / duplicate / failed
    notification_id: int | None = None


class ReminderService:
    """提醒规则的判定与投递记录写入（站内通道即收件箱）。"""

    def __init__(self, db: AsyncSession, reminder_hour: int | None = None):
        self.db = db
        self.reminder_hour = settings.REMINDER_HOUR if reminder_hour is None else reminder_hour

    # ---------- tick ----------
    async def tick(self, now_local: datetime.datetime) -> TickSummary:
        """对全部用户跑一遍当前支持的规则；返回本次判定与投递摘要。

        固定三条读查询（用户、当前计划、今日打卡）一次取齐，再在内存里逐用户判定：
        tick 每 60 秒跑一次，逐用户查询会让成本随用户数线性增长，违背「轻量 tick」边界。
        """
        summary = TickSummary()
        user_ids = (await self.db.execute(select(User.id))).scalars().all()
        summary.evaluated_users = len(user_ids)
        if not user_ids:
            return summary

        today = now_local.date()
        plans = await self._active_plans_by_user()
        checked_in = await self._checked_in_users(today)
        weekday = now_local.isoweekday()

        for user_id in user_ids:
            plan = plans.get(user_id)
            workout = PlanService._workout_for_weekday(plan, weekday) if plan else None
            context = TrainingDayContext(
                is_training_day=workout is not None and not workout.is_rest_day,
                has_checked_in_today=user_id in checked_in,
                focus=workout.focus if workout else None,
                estimated_duration=workout.estimated_duration if workout else None,
            )
            candidates = evaluate_daily_training(
                now_local, context, reminder_hour=self.reminder_hour
            )
            for candidate in candidates:
                result = await self._deliver(user_id, candidate, today)
                if result.outcome == "delivered":
                    summary.delivered += 1
                elif result.outcome == "duplicate":
                    summary.duplicates += 1
                else:
                    summary.failed += 1

        log_event(
            logger,
            EVENT_REMINDER_TICK_COMPLETED,
            message="提醒 tick 完成",
            **{
                FIELD_EVALUATED_USERS: summary.evaluated_users,
                FIELD_DELIVERED: summary.delivered,
                FIELD_DUPLICATES: summary.duplicates,
                FIELD_FAILED: summary.failed,
            },
        )
        return summary

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

    async def _deliver(
        self, user_id: int, candidate: ReminderCandidate, local_date: datetime.date
    ) -> DeliveryResult:
        delivery = ReminderDelivery(
            user_id=user_id,
            rule_code=candidate.rule_code,
            local_date=local_date,
            channel=CHANNEL_IN_APP,
            status=DELIVERY_STATUS_SENT,
            payload={
                "title": candidate.title,
                "body": candidate.body,
                "target_path": candidate.target_path,
                "params": candidate.params,
            },
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
                    FIELD_RULE_CODE: candidate.rule_code,
                    FIELD_ERROR_CLASS: type(exc).__name__,
                },
            )
            return DeliveryResult(outcome="failed")
        return DeliveryResult(outcome="delivered", notification_id=delivery.id)

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
