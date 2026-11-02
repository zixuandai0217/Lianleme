"""可查询的调整作业服务（工单 26，工单 27 追加 interrupt / resume）。

打卡只创建作业并投递评估，HTTP 响应绝不等待 Graph；评估结果全部回写数据库，
读取只依赖数据库事实。失败被收敛成稳定分类（``provider_error`` /
``invalid_input`` / ``persist_error`` / ``internal_error``）+ 稳定错误码，
供应商原文只进日志，不进入对外响应。

工单 27 在同一个作业上追加一条「等用户拍板」的分支：评估已经算出结论，但若命中
ADR-0004 的三个风险条件，**不发布**这次结论——同一事务里回滚计划改动与结论记录，
把作业挂成 ``pending_choice`` 并保存评估快照 + 三选一载荷。用户之后 resume 时用
保存的快照落地，不重新评估（重新评估会和当时展示的选项不一致）。

超时兜底有两条路径，共用同一个幂等落地操作（``_land_choice``）：

1. 创建中断时投递一个延迟任务（``_schedule_expiry``，强引用 + 取消安全）；
2. 读取 / 恢复时惰性收敛：``pending_choice`` 且已过 ``interrupt_expires_at``
   的作业在投影前先按推荐项落地，因此进程重启也不会卡在待确认。
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import (
    ERROR_CODE_ADJUSTMENT_PERSIST_FAILED,
    EVENT_PLAN_ADJUSTMENT_APPLIED,
    EVENT_PLAN_ADJUSTMENT_FAILED,
    EVENT_PLAN_ADJUSTMENT_INTERRUPT,
    EVENT_PLAN_ADJUSTMENT_TIMEOUT_DEFAULT,
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
from app.models.adjustment import PlanAdjustment, new_adjustment_id
from app.models.adjustment_job import (
    CHOSEN_BY_TIMEOUT_DEFAULT,
    CHOSEN_BY_USER,
    ERROR_CODE_ALREADY_DECIDED,
    ERROR_CODE_JOB_FORBIDDEN,
    ERROR_CODE_JOB_NOT_FOUND,
    ERROR_CODE_LANDING_FAILED,
    ERROR_CODE_NOT_PENDING,
    ERROR_CODE_OPTION_INVALID,
    ERROR_CODE_TIMEOUT_FALLBACK_FAILED,
    JOB_STATUS_APPLIED,
    JOB_STATUS_EVALUATING,
    JOB_STATUS_EXPIRED_NO_CHOICE,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING_CHOICE,
    PENDING_JOB_STATUSES,
    PlanAdjustmentJob,
    is_stale_evaluating,
    new_job_id,
)
from app.models.plan import TrainingPlan
from app.models.user import User
from app.schemas.plan import TrainingPlanSchema
from app.services.ai.adjust_analyzers import InvalidAnalyzerInput
from app.services.ai.adjust_graph import apply_direction
from app.services.plan.interrupt_policy import (
    DIRECTION_DECREASE,
    DIRECTION_INCREASE,
    INTERRUPT_TTL_SECONDS,
    InterruptSignal,
    build_interrupt_payload,
    build_landed_reason,
    detect_interrupt,
    find_option,
    option_effect,
    recommended_option,
)
from app.services.plan.plan_service import PlanService

logger = logging.getLogger(__name__)

FAILURE_CLASS_PROVIDER = "provider_error"
FAILURE_CLASS_INVALID_INPUT = "invalid_input"
FAILURE_CLASS_PERSIST = "persist_error"
FAILURE_CLASS_INTERNAL = "internal_error"

ERROR_CODE_NO_ACTIVE_PLAN = "no_active_plan"
ERROR_CODE_INVALID_INPUT = "invalid_evaluation_input"
ERROR_CODE_INTERNAL = "adjustment_evaluation_failed"

# 本批次不允许改 ``core/logging.py``：新事件名先作为局部常量，交由 Lead 收编。

# 延迟兜底任务的强引用：asyncio 只持弱引用，事件循环可能在任务完成前回收它。
# 用列表而不是 set：测试里的 create_task 替身是不可哈希的简单对象。
_timeout_tasks: list = []
# 单独绑定 sleep / CancelledError，测试可以替换而不影响事件循环本身。
_async_sleep = asyncio.sleep
_CANCELLED_ERROR = asyncio.CancelledError

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


def _as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    """SQLite 读回的是 naive 时间：统一按 UTC 解释后再比较。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class NoActivePlanError(RuntimeError):
    """落地时已经没有可调整的计划：按失败收敛，绝不把作业卡在待确认。"""


class AdjustmentResumeRejected(Exception):
    """resume 的稳定拒绝：路由层把它翻译成 HTTPException，不泄漏内部细节。"""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _forget_timeout_task(task: object) -> None:
    try:
        _timeout_tasks.remove(task)
    except ValueError:
        pass


def _schedule_expiry(job_id: str, delay_seconds: float) -> None:
    """投递「到点按推荐方案落地」的延迟任务；没有事件循环时交给惰性收敛。"""
    try:
        task = asyncio.create_task(_expire_job_after(job_id, delay_seconds))
    except Exception:  # noqa: BLE001 - 投递失败由读取时的惰性收敛兜底
        return
    _timeout_tasks.append(task)
    add_done_callback = getattr(task, "add_done_callback", None)
    if callable(add_done_callback):
        add_done_callback(_forget_timeout_task)


async def _expire_job_after(job_id: str, delay_seconds: float) -> None:
    """睡到窗口结束再收敛；取消（进程关停）时安静退出，幂等操作不会半途提交。"""
    try:
        if delay_seconds > 0:
            await _async_sleep(delay_seconds)
    except _CANCELLED_ERROR:  # pragma: no cover - 关停路径
        return
    try:
        async with AsyncSessionLocal() as session:
            await AdjustmentJobService(session).resolve_expired(job_id)
    except Exception as exc:  # noqa: BLE001 - 后台兜底失败不能冒泡到事件循环
        log_event(
            logger,
            EVENT_PLAN_ADJUSTMENT_FAILED,
            message="超时兜底未能落地",
            level=logging.WARNING,
            exc_info=exc,
            **{
                FIELD_JOB_ID: job_id,
                FIELD_ERROR_CODE: ERROR_CODE_TIMEOUT_FALLBACK_FAILED,
                FIELD_ERROR_CLASS: type(exc).__name__,
            },
        )


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
    """作业的创建、执行、只读查询与 interrupt / resume。"""

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
        job = await self.db.get(PlanAdjustmentJob, job_id)
        return await self._resolve_if_expired(job)

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
        jobs = list(result.scalars().all())
        for job in jobs:
            await self._resolve_if_expired(job)
        return jobs

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
        jobs = list(result.scalars().all())
        for job in jobs:
            await self._resolve_if_expired(job)
        # 崩溃遗留的 evaluating 不进入未决列表：它们在读取时已被投影为 failed。
        return [
            job
            for job in jobs
            if job.status in PENDING_JOB_STATUSES and not is_stale_evaluating(job)
        ]

    async def execute(
        self,
        job_id: str,
        *,
        completion_rate: float,
        difficulty_rating: float,
    ) -> PlanAdjustmentJob | None:
        """执行一次作业：评估 → (中断) 或 落盘 → 回写作业；失败只更新作业，不抛出。"""
        job = await self.db.get(PlanAdjustmentJob, job_id)
        if job is None or job.status != JOB_STATUS_EVALUATING:
            return job

        user_id = job.user_id
        plan_service = PlanService(self.db)
        before = await plan_service.get_current_plan(user_id)
        if before is None:
            await self._mark_failed(
                job,
                failure_class=FAILURE_CLASS_INVALID_INPUT,
                error_code=ERROR_CODE_NO_ACTIVE_PLAN,
                exc=None,
            )
            return job

        pending_job: PlanAdjustmentJob | None = None
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

            goal_conflict = await self._goal_conflict_flag(
                user_id, record.direction
            )
            if goal_conflict is not None:
                # 工单 24 修订：目标冲突红标志由工单 27 以同一形状追加。
                merged = _as_dict(record.merged)
                merged["red_flags"] = [
                    *_as_list(merged.get("red_flags")), goal_conflict
                ]
                record.merged = merged
                await self.db.flush()

            signal = detect_interrupt(
                dimensions=_as_list(record.dimensions),
                merged=_as_dict(record.merged),
                recent_deltas=await self._recent_applied_deltas(user_id),
            )
            if signal.triggered:
                evaluation = {
                    "completion_rate": float(completion_rate),
                    "difficulty_rating": _optional_float(difficulty_rating),
                    "dimensions": _as_list(record.dimensions),
                    "merged": _as_dict(record.merged),
                }
                # 结论已经算出但命中风险条件：整笔撤销（计划 + 结论记录），
                # 观察者只会看到「计划没变 + 作业等你拍板」。
                await self.db.rollback()
                pending = await self.db.get(PlanAdjustmentJob, job_id)
                if pending is None:
                    return None
                pending_job = await self._mark_pending_choice(
                    pending, signal=signal, evaluation=evaluation
                )
            else:
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
                job.chosen_by = None
                job.chosen_option = None
                await self.db.commit()
        except Exception as exc:  # noqa: BLE001 - 失败必须落成可查询作业，绝不冒泡
            await self.db.rollback()
            return await self._fail_existing_job(job_id, user_id, exc)

        if pending_job is not None:
            # 日志放在事务之外：已提交的 pending 事实不会被日志异常改写。
            log_event(
                logger,
                EVENT_PLAN_ADJUSTMENT_INTERRUPT,
                message="命中风险条件，调整挂起等待用户选择",
                **{
                    FIELD_USER_ID: user_id,
                    FIELD_JOB_ID: pending_job.job_id,
                    "reason_codes": ",".join(
                        _as_dict(pending_job.interrupt).get("reason_codes") or []
                    ),
                },
            )
            return pending_job

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

    async def resume(
        self, *, job_id: str, user_id: int, option_id: str
    ) -> tuple[PlanAdjustmentJob, PlanAdjustment | None]:
        """用户拍板：按所选项落地；重复同一选项幂等，改选项是冲突。"""
        job = await self.db.get(PlanAdjustmentJob, job_id)
        if job is None:
            raise AdjustmentResumeRejected(
                404, ERROR_CODE_JOB_NOT_FOUND, "找不到这条调整作业"
            )
        if job.user_id != user_id:
            raise AdjustmentResumeRejected(
                403, ERROR_CODE_JOB_FORBIDDEN, "无权访问其他用户的调整作业"
            )

        # 重启后没有延迟任务：投影前先把过期的待选择收敛成终态。
        job = await self._resolve_if_expired(job)
        if job is None:
            raise AdjustmentResumeRejected(
                404, ERROR_CODE_JOB_NOT_FOUND, "找不到这条调整作业"
            )

        if job.status == JOB_STATUS_EXPIRED_NO_CHOICE:
            # 超时兜底已经是终态：resume 只交代结果，不再改动计划。
            return job, await self.get_adjustment(job.adjustment_id)
        if job.status == JOB_STATUS_APPLIED:
            if job.chosen_option == option_id:
                return job, await self.get_adjustment(job.adjustment_id)
            raise AdjustmentResumeRejected(
                409,
                ERROR_CODE_ALREADY_DECIDED,
                "这次调整已经落地，不能再改成别的选项",
            )
        if job.status != JOB_STATUS_PENDING_CHOICE:
            raise AdjustmentResumeRejected(
                409, ERROR_CODE_NOT_PENDING, "这条调整当前不在待选择状态"
            )

        payload = job.interrupt if isinstance(job.interrupt, dict) else {}
        option = find_option(payload, option_id)
        if option is None:
            raise AdjustmentResumeRejected(
                422, ERROR_CODE_OPTION_INVALID, "选项不存在，请从 interrupt 载荷里选择"
            )
        evaluation = _as_dict(payload.get("evaluation"))

        try:
            await self._land_choice(
                job,
                option=option,
                evaluation=evaluation,
                chosen_by=CHOSEN_BY_USER,
                status=JOB_STATUS_APPLIED,
            )
        except Exception as exc:  # noqa: BLE001 - 落地失败给稳定 409，不留下半成品
            await self.db.rollback()
            raise AdjustmentResumeRejected(
                409, ERROR_CODE_LANDING_FAILED, "这次调整没能落地，请重试"
            ) from exc
        return job, await self.get_adjustment(job.adjustment_id)

    async def resolve_expired(self, job_id: str) -> PlanAdjustmentJob | None:
        """延迟任务与惰性收敛共用的入口：只有确实过期才会落地。"""
        job = await self.db.get(PlanAdjustmentJob, job_id)
        return await self._resolve_if_expired(job)

    # ------------------------------------------------------------------
    # interrupt：挂起、收敛与落地
    # ------------------------------------------------------------------

    async def _mark_pending_choice(
        self,
        job: PlanAdjustmentJob,
        *,
        signal: InterruptSignal,
        evaluation: dict,
    ) -> PlanAdjustmentJob:
        now = utc_now()
        job.status = JOB_STATUS_PENDING_CHOICE
        job.interrupt = build_interrupt_payload(signal, now=now, evaluation=evaluation)
        job.interrupt_expires_at = now + datetime.timedelta(
            seconds=INTERRUPT_TTL_SECONDS
        )
        job.adjustment_id = None
        job.landed_at = None
        job.decision = None
        job.plan_diff = None
        job.chosen_by = None
        job.chosen_option = None
        job.error_code = None
        job.failure_class = None
        await self.db.commit()
        _schedule_expiry(job.job_id, INTERRUPT_TTL_SECONDS)
        return job

    async def _resolve_if_expired(
        self, job: PlanAdjustmentJob | None, *, now: datetime.datetime | None = None
    ) -> PlanAdjustmentJob | None:
        if job is None or job.status != JOB_STATUS_PENDING_CHOICE:
            return job
        expires_at = _as_utc(job.interrupt_expires_at)
        if expires_at is None:
            return job
        moment = now or utc_now()
        if moment < expires_at:
            return job

        job_id = job.job_id
        user_id = job.user_id
        payload = job.interrupt if isinstance(job.interrupt, dict) else {}
        option = recommended_option(payload)
        evaluation = _as_dict(payload.get("evaluation"))
        try:
            await self._land_choice(
                job,
                option=option,
                evaluation=evaluation,
                chosen_by=CHOSEN_BY_TIMEOUT_DEFAULT,
                status=JOB_STATUS_EXPIRED_NO_CHOICE,
            )
        except NoActivePlanError:
            await self.db.rollback()
            reloaded = await self.db.get(PlanAdjustmentJob, job_id)
            if reloaded is not None:
                await self._mark_failed(
                    reloaded,
                    failure_class=FAILURE_CLASS_INVALID_INPUT,
                    error_code=ERROR_CODE_NO_ACTIVE_PLAN,
                    exc=None,
                )
            return reloaded
        except Exception as exc:  # noqa: BLE001 - 读取路径不能因兜底失败 500
            await self.db.rollback()
            return await self._fail_existing_job(job_id, user_id, exc)

        log_event(
            logger,
            EVENT_PLAN_ADJUSTMENT_TIMEOUT_DEFAULT,
            message="超时未选择，已按推荐方案代为落地",
            **{
                FIELD_USER_ID: user_id,
                FIELD_JOB_ID: job_id,
                FIELD_ADJUSTMENT_ID: job.adjustment_id,
                FIELD_DIRECTION: option_effect(option)[0],
            },
        )
        return job

    async def _land_choice(
        self,
        job: PlanAdjustmentJob,
        *,
        option: dict,
        evaluation: dict,
        chosen_by: str,
        status: str,
    ) -> PlanAdjustment:
        """把「所选方向 + 声明幅度」落到当前计划，并写一条可回看的调整结论。"""
        plan_service = PlanService(self.db)
        before = await plan_service.get_current_plan(job.user_id)
        if before is None or before.id is None:
            raise NoActivePlanError("没有可调整的当前计划")
        db_plan = await self.db.get(TrainingPlan, before.id)
        if db_plan is None:
            raise NoActivePlanError("没有可调整的当前计划")

        direction, magnitude = option_effect(option)
        # 与自动落地共用同一套缩放语义：只改整体难度系数，动作清单原样保留。
        scaled = apply_direction(
            {"difficulty_factor": db_plan.difficulty_factor or 1.0},
            direction,
            magnitude,
        )
        db_plan.difficulty_factor = scaled.get(
            "difficulty_factor", db_plan.difficulty_factor
        )

        merged = _as_dict(evaluation.get("merged"))
        record = PlanAdjustment(
            id=new_adjustment_id(),
            user_id=job.user_id,
            plan_id=before.id,
            direction=direction,
            reason=build_landed_reason(option, merged, chosen_by=chosen_by),
            completion_rate=_optional_float(evaluation.get("completion_rate")) or 0.0,
            difficulty_rating=_optional_float(evaluation.get("difficulty_rating")),
            overall_score=merged.get("overall_score"),
            delta_percent=magnitude,
            dimensions=_as_list(evaluation.get("dimensions")) or None,
            merged=merged or None,
        )
        self.db.add(record)
        db_plan.latest_adjustment_id = record.id
        await self.db.flush()

        job.status = status
        job.adjustment_id = record.id
        job.landed_at = utc_now()
        job.chosen_by = chosen_by
        job.chosen_option = str(option.get("id") or "") or None
        job.decision = {
            "direction": direction,
            "delta_percent": magnitude,
            "exercise_swaps": [],
            "rest_day_change": None,
        }
        job.plan_diff = build_plan_diff(before, db_plan)
        job.error_code = None
        job.failure_class = None
        await self.db.commit()
        # 提交后刷新，避免 onupdate 的服务端时间戳在响应投影时触发异步懒加载。
        await self.db.refresh(job)
        return record

    async def _goal_conflict_flag(
        self, user_id: int, direction: str
    ) -> dict | None:
        """档案目标与本次方向相反时，追加一个 goal_conflict 红标志。"""
        if direction not in (DIRECTION_INCREASE, DIRECTION_DECREASE):
            return None
        user = await self.db.get(User, user_id)
        profile = user.profile if isinstance(getattr(user, "profile", None), dict) else {}
        goal = str(profile.get("goal") or "").strip().lower()
        if not goal:
            return None
        if any(word in goal for word in ("减脂", "lose", "fat_loss")):
            conflicting = direction == DIRECTION_INCREASE
            direction_text = "上调"
        elif any(word in goal for word in ("增肌", "gain", "muscle")):
            conflicting = direction == DIRECTION_DECREASE
            direction_text = "下调"
        else:
            return None
        if not conflicting:
            return None
        return {
            "code": "goal_conflict",
            "severity": "medium",
            "evidence": (
                f"档案目标「{profile.get('goal')}」与本次调整方向（难度{direction_text}）相反"
            ),
        }

    async def _recent_applied_deltas(self, user_id: int) -> list[float]:
        """最近 3 次已落地作业的声明幅度（最近优先）；无法判定时返回空列表。"""
        result = await self.db.execute(
            select(PlanAdjustmentJob)
            .where(
                PlanAdjustmentJob.user_id == user_id,
                PlanAdjustmentJob.status == JOB_STATUS_APPLIED,
            )
            .order_by(desc(PlanAdjustmentJob.created_at), desc(PlanAdjustmentJob.job_id))
            .limit(3)
        )
        deltas: list[float] = []
        for job in result.scalars().all():
            decision = _as_dict(job.decision)
            delta = _optional_float(decision.get("delta_percent"))
            if delta is None:
                return []
            deltas.append(abs(delta))
        return deltas

    # ------------------------------------------------------------------
    # 失败收敛（工单 26 既有语义）
    # ------------------------------------------------------------------

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
        job.chosen_by = None
        job.chosen_option = None
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


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}
