"""可查询的调整作业服务（工单 26）。

打卡只创建作业并投递评估，HTTP 响应绝不等待 Graph；评估结果全部回写数据库，
读取只依赖数据库事实。失败被收敛成稳定分类（``provider_error`` /
``invalid_input`` / ``persist_error`` / ``internal_error``）+ 稳定错误码，
供应商原文只进日志，不进入对外响应。

``pending_choice`` / ``expired_no_choice`` 的写入属于工单 27；本服务读取这两个
状态时不需要任何改动。
"""
from __future__ import annotations

import datetime
import json
import logging

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import (
    ERROR_CODE_ADJUSTMENT_PERSIST_FAILED,
    EVENT_PLAN_ADJUSTMENT_APPLIED,
    EVENT_PLAN_ADJUSTMENT_FAILED,
    FIELD_ADJUSTMENT_ID,
    FIELD_COMPLETION_RATE,
    FIELD_DIRECTION,
    FIELD_ERROR_CLASS,
    FIELD_ERROR_CODE,
    FIELD_FAILURE_CLASS,
    FIELD_JOB_ID,
    FIELD_PLAN_ID,
    FIELD_USER_ID,
    log_event,
)
from app.models.adjustment import PlanAdjustment
from app.models.adjustment_job import (
    JOB_STATUS_APPLIED,
    JOB_STATUS_EVALUATING,
    JOB_STATUS_FAILED,
    PENDING_JOB_STATUSES,
    PlanAdjustmentJob,
    is_stale_evaluating,
    new_job_id,
)
from app.models.plan import TrainingPlan
from app.schemas.plan import TrainingPlanSchema
from app.services.ai.adjust_analyzers import InvalidAnalyzerInput
from app.services.plan.plan_service import PlanService

logger = logging.getLogger(__name__)

FAILURE_CLASS_PROVIDER = "provider_error"
FAILURE_CLASS_INVALID_INPUT = "invalid_input"
FAILURE_CLASS_PERSIST = "persist_error"
FAILURE_CLASS_INTERNAL = "internal_error"

ERROR_CODE_NO_ACTIVE_PLAN = "no_active_plan"
ERROR_CODE_INVALID_INPUT = "invalid_evaluation_input"
ERROR_CODE_INTERNAL = "adjustment_evaluation_failed"

_PROVIDER_HINTS = (
    "api key",
    "apikey",
    "401",
    "403",
    "unauthorized",
    "authentication",
    "rate limit",
    "429",
    "timeout",
    "timed out",
    "504",
    "provider",
    "openai",
    "anthropic",
    "llm",
)
_PERSIST_HINTS = (
    "database",
    "db ",
    "sqlalchemy",
    "persist",
    "commit",
    "connection",
    "store",
)


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _provider_error_code(text: str) -> str:
    if any(hint in text for hint in ("timeout", "timed out", "504")):
        return "provider_timeout"
    if any(hint in text for hint in ("rate limit", "429")):
        return "provider_rate_limited"
    if any(
        hint in text
        for hint in ("api key", "apikey", "401", "403", "unauthorized", "authentication")
    ):
        return "provider_auth_failed"
    return "provider_error"


def classify_failure(exc: BaseException) -> tuple[str, str]:
    """把评估异常收敛成稳定失败分类 + 稳定错误码（不泄漏原文）。"""
    if isinstance(exc, InvalidAnalyzerInput):
        return FAILURE_CLASS_INVALID_INPUT, ERROR_CODE_INVALID_INPUT
    if isinstance(exc, SQLAlchemyError):
        return FAILURE_CLASS_PERSIST, ERROR_CODE_ADJUSTMENT_PERSIST_FAILED

    text = f"{type(exc).__name__}: {exc}".lower()
    if any(hint in text for hint in _PROVIDER_HINTS):
        return FAILURE_CLASS_PROVIDER, _provider_error_code(text)
    if isinstance(exc, (ValueError, TypeError)):
        return FAILURE_CLASS_INVALID_INPUT, ERROR_CODE_INVALID_INPUT
    if any(hint in text for hint in _PERSIST_HINTS):
        return FAILURE_CLASS_PERSIST, ERROR_CODE_ADJUSTMENT_PERSIST_FAILED
    return FAILURE_CLASS_INTERNAL, ERROR_CODE_INTERNAL


def build_plan_diff(
    before: TrainingPlanSchema | None, after: TrainingPlan | None
) -> dict:
    """评估时快照计划前后差异；副本落库，之后计划再变也不改写这次交代。"""
    before_factor = float(before.difficulty_factor or 1.0) if before else 1.0
    after_factor = (
        float(after.difficulty_factor) if after and after.difficulty_factor is not None
        else before_factor
    )
    before_days = [day.model_dump() for day in before.weekly_plan] if before else []
    after_days = list(after.weekly_plan or []) if after else []

    before_by_day = {
        _day_number(entry): entry for entry in before_days if _day_number(entry) is not None
    }
    after_by_day = {
        _day_number(entry): entry for entry in after_days if _day_number(entry) is not None
    }
    changed_days = sorted(
        day
        for day in set(before_by_day) | set(after_by_day)
        if _canonical(before_by_day.get(day)) != _canonical(after_by_day.get(day))
    )
    return {
        "before_difficulty_factor": before_factor,
        "after_difficulty_factor": after_factor,
        "before_summary": f"{len(before_days)} 天计划，难度系数 {before_factor:.2f}",
        "after_summary": f"{len(after_days)} 天计划，难度系数 {after_factor:.2f}",
        "changed_days": changed_days,
    }


def _day_number(entry: object) -> int | None:
    if not isinstance(entry, dict):
        return None
    day = entry.get("day")
    return day if isinstance(day, int) else None


def _canonical(entry: object) -> str:
    return json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str)


class AdjustmentJobService:
    """作业的创建、执行与只读查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, user_id: int) -> PlanAdjustmentJob:
        """登记一条评估中作业；调用方负责提交（与打卡事务分离）。"""
        job = PlanAdjustmentJob(
            job_id=new_job_id(),
            user_id=user_id,
            status=JOB_STATUS_EVALUATING,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_job(self, job_id: str) -> PlanAdjustmentJob | None:
        """按标识读取任意用户的作业；权限判断留给路由层（403 不泄漏内容）。"""
        return await self.db.get(PlanAdjustmentJob, job_id)

    async def get_adjustment(self, adjustment_id: str | None) -> PlanAdjustment | None:
        if not adjustment_id:
            return None
        return await self.db.get(PlanAdjustment, adjustment_id)

    async def list_jobs(self, user_id: int, limit: int = 20) -> list[PlanAdjustmentJob]:
        """最近作业，倒序；同秒内按时间有序的 job_id 兜底。"""
        result = await self.db.execute(
            select(PlanAdjustmentJob)
            .where(PlanAdjustmentJob.user_id == user_id)
            .order_by(desc(PlanAdjustmentJob.created_at), desc(PlanAdjustmentJob.job_id))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_pending(self, user_id: int) -> list[PlanAdjustmentJob]:
        """当前用户未决作业（评估中 / 待选择），无未决时返回空列表。"""
        result = await self.db.execute(
            select(PlanAdjustmentJob)
            .where(
                PlanAdjustmentJob.user_id == user_id,
                PlanAdjustmentJob.status.in_(PENDING_JOB_STATUSES),
            )
            .order_by(desc(PlanAdjustmentJob.created_at), desc(PlanAdjustmentJob.job_id))
        )
        # 崩溃遗留的 evaluating 不进入未决列表：它们在读取时已被投影为 failed。
        return [job for job in result.scalars().all() if not is_stale_evaluating(job)]

    async def execute(
        self,
        job_id: str,
        *,
        completion_rate: float,
        difficulty_rating: float,
    ) -> PlanAdjustmentJob | None:
        """执行一次作业：评估 → 落盘 → 回写作业；失败只更新作业，不抛出。"""
        job = await self.db.get(PlanAdjustmentJob, job_id)
        if job is None or job.status != JOB_STATUS_EVALUATING:
            return job

        user_id = job.user_id
        plan_service = PlanService(self.db)
        before = await plan_service.get_current_plan(user_id)

        try:
            record = await plan_service.adjust_plan_after_workout(
                user_id=user_id,
                completion_rate=completion_rate,
                difficulty_rating=difficulty_rating,
            )
            if record is None:
                await self._mark_failed(
                    job,
                    failure_class=FAILURE_CLASS_INVALID_INPUT,
                    error_code=ERROR_CODE_NO_ACTIVE_PLAN,
                    exc=None,
                )
                return job

            after = await self.db.get(TrainingPlan, record.plan_id)
            record_id = record.id
            record_plan_id = record.plan_id
            record_direction = record.direction
            job.status = JOB_STATUS_APPLIED
            job.adjustment_id = record_id
            job.landed_at = utc_now()
            job.decision = {
                "direction": record_direction,
                "delta_percent": float(record.delta_percent or 0.0),
                # 工单 24 的 Graph 不产出动作替换 / 休息日变更：如实为空，不伪造。
                "exercise_swaps": [],
                "rest_day_change": None,
            }
            job.plan_diff = build_plan_diff(before, after)
            job.error_code = None
            job.failure_class = None
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001 - 失败必须落成可查询作业，绝不冒泡
            await self.db.rollback()
            return await self._fail_existing_job(job_id, user_id, exc)

        log_event(
            logger,
            EVENT_PLAN_ADJUSTMENT_APPLIED,
            message="计划调整已落盘",
            **{
                FIELD_USER_ID: user_id,
                FIELD_ADJUSTMENT_ID: record_id,
                FIELD_PLAN_ID: record_plan_id,
                FIELD_DIRECTION: record_direction,
                FIELD_COMPLETION_RATE: round(completion_rate, 4),
            },
        )
        return job

    async def _fail_existing_job(
        self, job_id: str, user_id: int, exc: BaseException
    ) -> PlanAdjustmentJob | None:
        """回滚后重新加载作业并写入失败事实（job 行本身在更早的事务里已提交）。"""
        job = await self.db.get(PlanAdjustmentJob, job_id)
        if job is None:
            return None
        failure_class, error_code = classify_failure(exc)
        await self._mark_failed(
            job,
            failure_class=failure_class,
            error_code=error_code,
            exc=exc,
            user_id=user_id,
        )
        return job

    async def _mark_failed(
        self,
        job: PlanAdjustmentJob,
        *,
        failure_class: str,
        error_code: str,
        exc: BaseException | None,
        user_id: int | None = None,
    ) -> None:
        job.status = JOB_STATUS_FAILED
        job.failure_class = failure_class
        job.error_code = error_code
        job.landed_at = None
        job.decision = None
        job.plan_diff = None
        await self.db.commit()

        resolved_user_id = user_id if user_id is not None else job.user_id
        event_fields = {
            FIELD_USER_ID: resolved_user_id,
            FIELD_ERROR_CODE: error_code,
            FIELD_ERROR_CLASS: type(exc).__name__ if exc is not None else "NoActivePlan",
            FIELD_FAILURE_CLASS: failure_class,
            FIELD_JOB_ID: job.job_id,
        }
        log_event(
            logger,
            EVENT_PLAN_ADJUSTMENT_FAILED,
            message="打卡后的计划调整未能落盘",
            level=logging.WARNING,
            exc_info=exc,
            **event_fields,
        )
