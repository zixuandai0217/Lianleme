"""
WorkoutService：训练完成数据上报、打卡记录存储、四段式反馈与连续打卡统计

打卡只做两件事：写入「已完成的训练事实」，并投递一条可查询的计划调整作业。
评估是否完成、是否失败都不阻塞打卡；反馈里的计划影响是对作业 / 调整结论的投影，
不复制第二份理由文本。
"""
import asyncio
import datetime
import logging

from langchain_core.messages import HumanMessage
from sqlalchemy import desc, extract, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import (
    ERROR_CODE_ADJUSTMENT_PERSIST_FAILED,
    EVENT_PLAN_ADJUSTMENT_FAILED,
    FIELD_ERROR_CLASS,
    FIELD_ERROR_CODE,
    FIELD_USER_ID,
    log_event,
)
from app.models.adjustment_job import (
    JOB_STATUS_APPLIED,
    JOB_STATUS_EVALUATING,
    JOB_STATUS_EXPIRED_NO_CHOICE,
    JOB_STATUS_PENDING_CHOICE,
    effective_status,
)
from app.models.record import WorkoutRecord
from app.models.workout_session import WorkoutSession
from app.schemas.workout import (
    CheckInStatsResponse,
    FeedbackComparison,
    FeedbackCompletion,
    FeedbackPlanImpact,
    FeedbackRecovery,
    WorkoutCompleteRequest,
    WorkoutFeedback,
    WorkoutRecordResponse,
)
from app.services.ai import llm_observability as observed
from app.services.ai.llm_factory import LLMClientFactory
from app.services.plan.adjustment_job_service import AdjustmentJobService

logger = logging.getLogger(__name__)

# 保留后台任务强引用：asyncio 只持弱引用，事件循环可能在任务完成前回收它。
# 用列表而不是 set：测试里的 create_task 替身是不可哈希的简单对象。
_background_tasks: list = []


def _forget_background_task(task: object) -> None:
    """任务完成后从强引用表里移除；替身对象不在表里时静默跳过。"""
    try:
        _background_tasks.remove(task)
    except ValueError:
        pass

# 作业没建成时给调用方的稳定原因；打卡本身仍然成功。
JOB_NOT_CREATED = "job_not_created"

# 计划影响状态（对外稳定枚举）：投影自作业当前状态，不是第二份存储。
PLAN_IMPACT_NOT_DISPATCHED = "not_dispatched"
PLAN_IMPACT_EVALUATING = "evaluating"
PLAN_IMPACT_PENDING_CHOICE = "pending_choice"
PLAN_IMPACT_EXPIRED_NO_CHOICE = "expired_no_choice"
PLAN_IMPACT_APPLIED = "applied"
PLAN_IMPACT_FAILED = "failed"

PLAN_IMPACT_EVALUATING_REASON = "本次评估还在进行，稍后可在计划页看到结论"
PLAN_IMPACT_PENDING_CHOICE_REASON = "等你确认风险处理方式后才会生效"
PLAN_IMPACT_FAILED_REASON = "本次调整评估失败，计划没有改变"
PLAN_IMPACT_EXPIRED_NO_CHOICE_REASON = (
    "5 分钟未确认，已按推荐（保守）方案自动应用，计划已更新"
)
PLAN_IMPACT_NOT_DISPATCHED_REASON = "本次打卡没有投递调整作业，计划保持原样"
PLAN_IMPACT_MISSING_JOB_REASON = "找不到这次调整作业，计划没有改变"

DIRECTIONS = ("increase", "decrease", "keep")


def _text(value: object) -> str | None:
    """把快照里的自由值收敛成可读文本；异常形态降级为 None。"""
    if isinstance(value, str):
        return value.strip() or None
    return None


def _as_percent_points(delta: float) -> float:
    """完成率差以「百分点」表达：0.8 → 0.6 是 -20.0，而不是 -25%。"""
    return round(delta * 100, 1)


class WorkoutService:
    """训练记录核心服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.factory = LLMClientFactory(db)

    async def complete_workout(self, req: WorkoutCompleteRequest) -> WorkoutRecordResponse:
        """上报训练完成数据：写记录、投递作业、立即返回四段式反馈。

        重复打卡（同一用户同一天）返回已有记录与同一作业，不新建第二条事实，
        也不重复投递评估。
        """
        existing = await self._existing_record(req.user_id, req.workout_date)
        if existing is not None:
            return await self._build_response(existing)

        session = await self._session_for(req.user_id, req.workout_date)
        total_sets, completed_sets = self._completion_counts(session, req)
        completion_rate = completed_sets / total_sets if total_sets > 0 else 0.0

        ai_feedback, recovery_source = await self._generate_feedback(
            user_id=req.user_id,
            completion_rate=completion_rate,
            duration=req.duration_minutes,
            detail=req.detail,
        )

        record = WorkoutRecord(
            user_id=req.user_id,
            plan_id=req.plan_id or (session.plan_id if session is not None else None),
            workout_date=req.workout_date,
            total_sets=total_sets,
            completed_sets=completed_sets,
            completion_rate=completion_rate,
            duration_minutes=req.duration_minutes,
            difficulty_rating=req.difficulty_rating,
            detail=req.detail,
            ai_feedback=ai_feedback,
        )
        if session is not None:
            # 打卡是会话的收尾动作：只有进行中的会话会被收敛为已完成。
            if session.status == "in_progress":
                session.status = "completed"
                session.ended_at = datetime.datetime.now(datetime.timezone.utc)
                session.last_activity_at = session.ended_at
            session.total_sets = total_sets
            session.completed_sets = completed_sets
        self.db.add(record)
        await self.db.flush()

        # 作业放在 savepoint 里创建：成功则与打卡一起提交（原子），失败只回滚作业，
        # 打卡本身照常成功——不会出现「作业已提交但打卡记录没指向它」的半截事实。
        job_id, job_error = await self._create_adjustment_job(req)
        record.adjustment_job_id = job_id
        record.plan_impact_status = (
            PLAN_IMPACT_EVALUATING if job_id is not None else PLAN_IMPACT_NOT_DISPATCHED
        )
        try:
            await self.db.commit()
        except IntegrityError:
            # 并发同一天重复打卡：数据库唯一索引兜底，返回已经存在的那条事实。
            await self.db.rollback()
            existing = await self._existing_record(req.user_id, req.workout_date)
            if existing is None:
                raise
            return await self._build_response(existing)

        if job_id is not None:
            # 只投递，不等待评估完成；评估结果回写到作业，供之后查询。
            task = asyncio.create_task(
                self._trigger_plan_adjustment(
                    job_id=job_id,
                    user_id=req.user_id,
                    completion_rate=completion_rate,
                    difficulty_rating=float(req.difficulty_rating or 3),
                )
            )
            _background_tasks.append(task)
            # 测试替身没有 add_done_callback；真实 Task 才有清理回调。
            add_done_callback = getattr(task, "add_done_callback", None)
            if callable(add_done_callback):
                add_done_callback(_forget_background_task)

        return await self._build_response(
            record,
            recovery_source=recovery_source,
            job_error=job_error,
        )

    async def _existing_record(
        self, user_id: int, workout_date: datetime.date
    ) -> WorkoutRecord | None:
        """同一用户同一天只认一条打卡事实：重复提交返回它，而不是再写一条。"""
        result = await self.db.execute(
            select(WorkoutRecord)
            .where(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date == workout_date,
            )
            .order_by(WorkoutRecord.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _session_for(
        self, user_id: int, workout_date: datetime.date
    ) -> WorkoutSession | None:
        result = await self.db.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.session_date == workout_date,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _completion_counts(
        session: WorkoutSession | None, req: WorkoutCompleteRequest
    ) -> tuple[int, int]:
        """有会话时以会话明细为准；没有会话才退回请求值（旧的手工填报路径）。"""
        if session is None:
            return req.total_sets, req.completed_sets

        exercises = session.exercises if isinstance(session.exercises, list) else []
        planned = 0
        completed = 0
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue
            try:
                planned += max(int(exercise.get("sets") or 0), 0)
                completed += max(int(exercise.get("completed_sets") or 0), 0)
            except (TypeError, ValueError):
                continue
        if planned <= 0:
            planned = max(int(session.total_sets or 0), 0)
            completed = max(int(session.completed_sets or 0), 0)
        if planned <= 0:
            return 0, 0
        return planned, min(completed, planned)

    async def _create_adjustment_job(
        self, req: WorkoutCompleteRequest
    ) -> tuple[str | None, str | None]:
        """在 savepoint 里创建可查询作业；失败只回滚作业，打卡事务保持完整。"""
        try:
            async with self.db.begin_nested():
                job = await AdjustmentJobService(self.db).create_job(req.user_id)
            return job.job_id, None
        except Exception as exc:  # noqa: BLE001 - 作业是附加事实，不能拖垮打卡
            log_event(
                logger,
                EVENT_PLAN_ADJUSTMENT_FAILED,
                message="打卡后的调整作业未能创建",
                level=logging.WARNING,
                exc_info=exc,
                **{
                    FIELD_USER_ID: req.user_id,
                    FIELD_ERROR_CODE: ERROR_CODE_ADJUSTMENT_PERSIST_FAILED,
                    FIELD_ERROR_CLASS: type(exc).__name__,
                },
            )
            return None, JOB_NOT_CREATED

    async def _build_response(
        self,
        record: WorkoutRecord,
        *,
        recovery_source: str | None = None,
        job_error: str | None = None,
    ) -> WorkoutRecordResponse:
        """把已落库的打卡记录投影成响应；每次读取都重新读作业的当前状态。"""
        previous = await self._previous_record(record)
        job_id = record.adjustment_job_id
        if job_error is None and job_id is None and record.plan_impact_status != "evaluating":
            job_error = JOB_NOT_CREATED

        recovery = self._project_recovery(record, recovery_source)
        completion = FeedbackCompletion(
            completed_sets=record.completed_sets,
            total_sets=record.total_sets,
            completion_rate=record.completion_rate,
            duration_minutes=record.duration_minutes,
        )
        feedback = WorkoutFeedback(
            completion=completion,
            comparison=self._project_comparison(record, previous),
            recovery=recovery,
            plan_impact=await self._project_plan_impact(record, job_id),
        )
        return WorkoutRecordResponse(
            id=record.id,
            workout_date=record.workout_date,
            completion_rate=record.completion_rate,
            duration_minutes=record.duration_minutes,
            ai_feedback=record.ai_feedback,
            job_id=job_id,
            job_error=job_error,
            feedback=feedback,
        )

    async def _previous_record(self, record: WorkoutRecord) -> WorkoutRecord | None:
        """上一条打卡（严格早于本次日期），用于对比段。"""
        result = await self.db.execute(
            select(WorkoutRecord)
            .where(
                WorkoutRecord.user_id == record.user_id,
                WorkoutRecord.workout_date < record.workout_date,
            )
            .order_by(desc(WorkoutRecord.workout_date), desc(WorkoutRecord.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _project_comparison(
        record: WorkoutRecord, previous: WorkoutRecord | None
    ) -> FeedbackComparison:
        if previous is None:
            # 首次训练没有可比较对象：不给方向、不给差值，避免伪造「提升 100%」。
            return FeedbackComparison(
                has_previous=False,
                previous_completion_rate=None,
                delta_percent=None,
                delta_points=None,
                direction="first_time",
            )
        delta = _as_percent_points(record.completion_rate - previous.completion_rate)
        if delta > 0:
            direction = "up"
        elif delta < 0:
            direction = "down"
        else:
            direction = "flat"
        return FeedbackComparison(
            has_previous=True,
            previous_completion_rate=previous.completion_rate,
            delta_percent=delta,
            delta_points=delta,
            direction=direction,
        )

    def _project_recovery(
        self, record: WorkoutRecord, source: str | None
    ) -> FeedbackRecovery:
        """恢复建议：模型文案可用就用它，否则给确定性兜底列表；永不为空。"""
        fallback_tips = self._fallback_tips(
            record.completion_rate, record.difficulty_rating
        )
        feedback = (record.ai_feedback or "").strip()

        if source is not None:
            if source == "model" and feedback:
                return FeedbackRecovery(source="model", tips=[feedback])
            return FeedbackRecovery(source="fallback", tips=fallback_tips)

        # 重复读取历史记录时没有来源标记：只有与兜底文案逐字相同时才判为 fallback。
        if feedback and feedback != self._fallback_feedback(
            record.completion_rate, record.difficulty_rating
        ):
            return FeedbackRecovery(source="model", tips=[feedback])
        return FeedbackRecovery(source="fallback", tips=fallback_tips)

    @staticmethod
    def _fallback_tips(completion_rate: float, difficulty: int | None) -> list[str]:
        if completion_rate >= 0.9:
            tips = ["完成度很稳，下次保持动作质量，不用急着加重量。"]
        elif completion_rate >= 0.6:
            tips = ["今天完成了一大半，下次优先补齐没做完的动作。"]
        else:
            tips = ["今天完成率偏低，下次少排一个动作，先把节奏找回来。"]
        if (difficulty or 3) >= 4:
            tips.append("自评强度偏高，接下来 48 小时安排拉伸和睡眠，别连着硬练。")
        else:
            tips.append("补够水，睡够 7 小时，让肌肉在恢复里长。")
        tips.append("训练后 30 分钟内补充蛋白质，明天用轻量活动恢复。")
        return tips

    @staticmethod
    def _fallback_feedback(
        completion_rate: float, difficulty: int | None = None
    ) -> str:
        """兜底文案与阶数无关：重复读取时才能稳定识别「这是 fallback 而不是模型」。"""
        return f"本次完成率 {completion_rate:.0%}，先把补水和睡眠做好，下一次继续。"

    async def _project_plan_impact(
        self, record: WorkoutRecord, job_id: str | None
    ) -> FeedbackPlanImpact:
        """投影调整作业的当前状态；评估没完成或失败都不影响打卡响应。"""
        if job_id is None:
            # 没有作业可读时回落到提交时刻的快照（正常是 not_dispatched）。
            snapshot = record.plan_impact_status or PLAN_IMPACT_NOT_DISPATCHED
            if snapshot not in (PLAN_IMPACT_NOT_DISPATCHED, PLAN_IMPACT_EVALUATING):
                snapshot = PLAN_IMPACT_NOT_DISPATCHED
            return FeedbackPlanImpact(
                status=snapshot,
                job_id=None,
                direction=None,
                reason=PLAN_IMPACT_NOT_DISPATCHED_REASON,
            )

        service = AdjustmentJobService(self.db)
        job = await service.get_job(job_id)
        if job is None:
            return FeedbackPlanImpact(
                status=PLAN_IMPACT_FAILED,
                job_id=job_id,
                direction=None,
                reason=PLAN_IMPACT_MISSING_JOB_REASON,
            )

        status = effective_status(job)
        if status == JOB_STATUS_PENDING_CHOICE:
            return FeedbackPlanImpact(
                status=PLAN_IMPACT_PENDING_CHOICE,
                job_id=job_id,
                direction=None,
                reason=PLAN_IMPACT_PENDING_CHOICE_REASON,
            )
        if status == JOB_STATUS_EVALUATING:
            return FeedbackPlanImpact(
                status=PLAN_IMPACT_EVALUATING,
                job_id=job_id,
                direction=None,
                reason=PLAN_IMPACT_EVALUATING_REASON,
            )
        if status == JOB_STATUS_EXPIRED_NO_CHOICE:
            # 超时兜底确实落地了计划，但必须与「用户选择后落地」区分开。
            adjustment = await service.get_adjustment(job.adjustment_id)
            direction = None
            if adjustment is not None and adjustment.direction in DIRECTIONS:
                direction = adjustment.direction  # type: ignore[assignment]
            job_diff = job.plan_diff if isinstance(job.plan_diff, dict) else {}
            return FeedbackPlanImpact(
                status=PLAN_IMPACT_EXPIRED_NO_CHOICE,
                job_id=job_id,
                direction=direction,
                reason=PLAN_IMPACT_EXPIRED_NO_CHOICE_REASON,
                before_summary=_text(job_diff.get("before_summary")),
                after_summary=_text(job_diff.get("after_summary")),
            )
        if status != JOB_STATUS_APPLIED:
            return FeedbackPlanImpact(
                status=PLAN_IMPACT_FAILED,
                job_id=job_id,
                direction=None,
                reason=PLAN_IMPACT_FAILED_REASON,
            )

        # 已落地：方向与理由必须来自与计划解释卡相同的那条调整结论。
        adjustment = await service.get_adjustment(job.adjustment_id)
        direction = None
        reason = "本次调整已应用"
        if adjustment is not None:
            if adjustment.direction in DIRECTIONS:
                direction = adjustment.direction  # type: ignore[assignment]
            reason = adjustment.reason

        plan_diff = job.plan_diff if isinstance(job.plan_diff, dict) else {}
        return FeedbackPlanImpact(
            status=PLAN_IMPACT_APPLIED,
            job_id=job_id,
            direction=direction,
            reason=reason,
            before_summary=_text(plan_diff.get("before_summary")),
            after_summary=_text(plan_diff.get("after_summary")),
        )

    async def get_stats(self, user_id: int) -> CheckInStatsResponse:
        """获取用户打卡统计数据"""
        today = datetime.date.today()

        # 总打卡次数
        total_result = await self.db.execute(
            select(func.count()).where(WorkoutRecord.user_id == user_id)
        )
        total = total_result.scalar() or 0

        # 连续打卡天数
        streak = await self._calc_streak(user_id)

        # 本月统计
        monthly_result = await self.db.execute(
            select(func.count(), func.avg(WorkoutRecord.completion_rate)).where(
                WorkoutRecord.user_id == user_id,
                extract("year", WorkoutRecord.workout_date) == today.year,
                extract("month", WorkoutRecord.workout_date) == today.month,
            )
        )
        monthly_count, monthly_avg = monthly_result.one()

        # 最近 5 条记录：顺带投影四段反馈，刷新 / 重新进入时仍能读到最新作业状态。
        recent_result = await self.db.execute(
            select(WorkoutRecord)
            .where(WorkoutRecord.user_id == user_id)
            .order_by(desc(WorkoutRecord.workout_date))
            .limit(5)
        )
        recent = [
            await self._build_response(record)
            for record in recent_result.scalars().all()
        ]

        return CheckInStatsResponse(
            total_checkins=total,
            streak_days=streak,
            monthly_checkins=monthly_count or 0,
            monthly_completion_rate=float(monthly_avg or 0),
            recent_records=recent,
        )

    async def get_monthly_calendar(
        self, user_id: int, year: int, month: int
    ) -> dict:
        """获取指定月份的打卡日历数据"""
        result = await self.db.execute(
            select(WorkoutRecord.workout_date, WorkoutRecord.completion_rate).where(
                WorkoutRecord.user_id == user_id,
                extract("year", WorkoutRecord.workout_date) == year,
                extract("month", WorkoutRecord.workout_date) == month,
            )
        )
        rows = result.all()
        return {
            "year": year,
            "month": month,
            "checkins": {
                str(row.workout_date): {"completion_rate": float(row.completion_rate)}
                for row in rows
            },
        }

    async def _calc_streak(self, user_id: int) -> int:
        """计算连续打卡天数"""
        result = await self.db.execute(
            select(WorkoutRecord.workout_date)
            .where(WorkoutRecord.user_id == user_id)
            .order_by(desc(WorkoutRecord.workout_date))
            .limit(60)
        )
        dates = sorted({row.workout_date for row in result}, reverse=True)
        if not dates:
            return 0
        streak = 0
        today = datetime.date.today()
        expected = today
        for d in dates:
            if d == expected or d == expected - datetime.timedelta(days=1):
                streak += 1
                expected = d - datetime.timedelta(days=1)
            else:
                break
        return streak

    async def _generate_feedback(
        self, user_id: int, completion_rate: float, duration: int, detail: dict
    ) -> tuple[str, str]:
        """调用 LLM 生成训练后建议；失败时返回确定性兜底文案与来源标记。"""
        try:
            llm = await self.factory.get_client(user_id=user_id, model_type="chat")
            prompt = (
                f"用户刚完成训练：完成率 {completion_rate:.0%}，用时 {duration} 分钟。"
                f"请给出 50 字以内的鼓励性总结和恢复建议。"
            )
            response = await observed.invoke(llm, [HumanMessage(content=prompt)])
            text = (response.content or "").strip()
            if text:
                return text, "model"
        except Exception:
            pass
        return (
            self._fallback_feedback(completion_rate, None),
            "fallback",
        )

    async def _trigger_plan_adjustment(
        self,
        *,
        job_id: str,
        user_id: int,
        completion_rate: float,
        difficulty_rating: float,
    ) -> None:
        """执行一次调整作业（独立 session 避免冲突）。

        调整是打卡之后的独立事实：失败不回滚打卡、不向用户抛异常，而是把作业
        置为 ``failed``（带稳定失败分类）并记一条 warning。成功时作业置
        ``applied`` 并记一条 applied 事件，便于运营回答「这次打卡到底改没改计划」。
        """
        try:
            async with AsyncSessionLocal() as session:
                await AdjustmentJobService(session).execute(
                    job_id,
                    completion_rate=completion_rate,
                    difficulty_rating=difficulty_rating,
                )
        except Exception as exc:  # noqa: BLE001 - 后台任务最后的兜底
            log_event(
                logger,
                EVENT_PLAN_ADJUSTMENT_FAILED,
                message="打卡后的计划调整未能落盘",
                level=logging.WARNING,
                exc_info=exc,
                **{
                    FIELD_USER_ID: user_id,
                    FIELD_ERROR_CODE: ERROR_CODE_ADJUSTMENT_PERSIST_FAILED,
                    FIELD_ERROR_CLASS: type(exc).__name__,
                },
            )
