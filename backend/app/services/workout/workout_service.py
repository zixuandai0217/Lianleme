"""
WorkoutService：训练完成数据上报、打卡记录存储、连续打卡统计
训练完成后自动触发 AdjustGraph 计划动态调整
"""
import datetime
from typing import List

from langchain_core.messages import HumanMessage
from sqlalchemy import desc, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import WorkoutRecord
from app.schemas.workout import (
    CheckInStatsResponse,
    WorkoutCompleteRequest,
    WorkoutRecordResponse,
)
from app.services.ai.llm_factory import LLMClientFactory


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

        # 异步触发计划调整（不阻塞响应）
        import asyncio
        asyncio.create_task(
            self._trigger_plan_adjustment(
                user_id=req.user_id,
                completion_rate=completion_rate,
                difficulty_rating=float(req.difficulty_rating or 3),
            )
        )

        return WorkoutRecordResponse(
            id=record.id,
            workout_date=record.workout_date,
            completion_rate=completion_rate,
            duration_minutes=record.duration_minutes,
            ai_feedback=ai_feedback,
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
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception:
            return f"太棒了！本次完成率 {completion_rate:.0%}，注意充分补水和休息。"

    async def _trigger_plan_adjustment(
        self, user_id: int, completion_rate: float, difficulty_rating: float
    ) -> None:
        """异步触发计划调整（独立 session 避免冲突）"""
        from app.core.database import AsyncSessionLocal
        from app.services.plan.plan_service import PlanService
        async with AsyncSessionLocal() as session:
            plan_service = PlanService(session)
            await plan_service.adjust_plan_after_workout(
                user_id=user_id,
                completion_rate=completion_rate,
                difficulty_rating=difficulty_rating,
            )
            await session.commit()
