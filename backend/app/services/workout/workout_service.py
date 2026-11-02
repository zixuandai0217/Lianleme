"""
WorkoutService：训练完成数据上报、打卡记录存储、连续打卡统计
训练完成后自动触发 AdjustGraph 计划动态调整
"""
import asyncio
import datetime
import logging

from langchain_core.messages import HumanMessage
from sqlalchemy import desc, extract, func, select
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
from app.models.record import WorkoutRecord
from app.schemas.workout import (
    CheckInStatsResponse,
    WorkoutCompleteRequest,
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


class WorkoutService:
    """训练记录核心服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.factory = LLMClientFactory(db)

    async def complete_workout(self, req: WorkoutCompleteRequest) -> WorkoutRecordResponse:
        """上报训练完成数据，存库 + 触发计划调整 + 生成 AI 反馈"""
        completion_rate = (
            req.completed_sets / req.total_sets if req.total_sets > 0 else 0.0
        )

        # 生成 AI 训练后反馈
        ai_feedback = await self._generate_feedback(
            user_id=req.user_id,
            completion_rate=completion_rate,
            duration=req.duration_minutes,
            detail=req.detail,
        )

        record = WorkoutRecord(
            user_id=req.user_id,
            plan_id=req.plan_id,
            workout_date=req.workout_date,
            total_sets=req.total_sets,
            completed_sets=req.completed_sets,
            completion_rate=completion_rate,
            duration_minutes=req.duration_minutes,
            difficulty_rating=req.difficulty_rating,
            detail=req.detail,
            ai_feedback=ai_feedback,
        )
        self.db.add(record)
        await self.db.flush()

        # 打卡先落库：调整作业是打卡之后的独立事实，作业创建失败也不回滚打卡。
        await self.db.commit()

        job_id, job_error = await self._create_adjustment_job(req)
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

        return WorkoutRecordResponse(
            id=record.id,
            workout_date=record.workout_date,
            completion_rate=completion_rate,
            duration_minutes=record.duration_minutes,
            ai_feedback=ai_feedback,
            job_id=job_id,
            job_error=job_error,
        )

    async def _create_adjustment_job(
        self, req: WorkoutCompleteRequest
    ) -> tuple[str | None, str | None]:
        """创建可查询作业；失败返回稳定原因而不是让打卡请求失败。"""
        try:
            job = await AdjustmentJobService(self.db).create_job(req.user_id)
            await self.db.commit()
            return job.job_id, None
        except Exception as exc:  # noqa: BLE001 - 作业是附加事实，不能拖垮打卡
            await self.db.rollback()
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

        # 最近 5 条记录
        recent_result = await self.db.execute(
            select(WorkoutRecord)
            .where(WorkoutRecord.user_id == user_id)
            .order_by(desc(WorkoutRecord.workout_date))
            .limit(5)
        )
        recent = [
            WorkoutRecordResponse.model_validate(r)
            for r in recent_result.scalars().all()
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
    ) -> str:
        """调用 LLM 生成训练后 AI 反馈建议"""
        try:
            llm = await self.factory.get_client(user_id=user_id, model_type="chat")
            prompt = (
                f"用户刚完成训练：完成率 {completion_rate:.0%}，用时 {duration} 分钟。"
                f"请给出 50 字以内的鼓励性总结和恢复建议。"
            )
            response = await observed.invoke(llm, [HumanMessage(content=prompt)])
            return response.content
        except Exception:
            return f"太棒了！本次完成率 {completion_rate:.0%}，注意充分补水和休息。"

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
