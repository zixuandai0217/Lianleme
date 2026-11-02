"""
PlanService：训练计划存取、AI 生成计划、今日任务获取、周视图查询
"""
import datetime
from typing import Optional

from langchain.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.local_time import local_date
from app.models.adjustment import (
    ADJUSTMENT_DIRECTIONS,
    PlanAdjustment,
    new_adjustment_id,
)
from app.models.plan import TrainingPlan
from app.schemas.plan import (
    DailyWorkout,
    TodayWorkoutResponse,
    TrainingPlanSchema,
)
from app.services.ai import llm_observability as observed
from app.services.ai.adjust_graph import AdjustGraph
from app.services.ai.llm_factory import LLMClientFactory

# 休息日提示沿用原接口文案：前端空态与历史文案都依赖它，改文案属于产品决策而非本次契约变更。
REST_DAY_MESSAGE = "今日休息，好好恢复"


class PlanService:
    """训练计划核心服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.factory = LLMClientFactory(db)

    async def get_current_plan(self, user_id: int) -> Optional[TrainingPlanSchema]:
        """获取用户最新的 active 训练计划"""
        result = await self.db.execute(
            select(TrainingPlan)
            .where(TrainingPlan.user_id == user_id, TrainingPlan.status == "active")
            .order_by(desc(TrainingPlan.week_start))
            .limit(1)
        )
        plan = result.scalar_one_or_none()
        return self._to_schema(plan) if plan else None

    @staticmethod
    def _today() -> datetime.date:
        """The user-facing local date (single source of truth for "today")."""
        return local_date()

    async def get_workout_for_weekday(
        self, user_id: int, weekday: int
    ) -> Optional[DailyWorkout]:
        """读取当前计划里某个周几的安排；没有计划或没有该天条目时返回 None。

        提醒调度需要「按注入的本地时刻所在周几」判定，不能用系统日期，因此单独暴露
        按周几查询的能力，并让今日三态复用同一个查找函数，保证两条链路同一口径。
        """
        plan = await self.get_current_plan(user_id)
        if not plan:
            return None
        return self._workout_for_weekday(plan, weekday)

    @staticmethod
    def _workout_for_weekday(plan: TrainingPlanSchema, weekday: int) -> Optional[DailyWorkout]:
        """Pure lookup over an already-loaded plan (no extra query)."""
        return next((day for day in plan.weekly_plan if day.day == weekday), None)

    async def get_today_state(self, user_id: int) -> TodayWorkoutResponse:
        """把今日安排收敛成三态：训练日 / 休息日 / 无计划。

        判定顺序：没有 active 计划 → 无计划；当天条目是休息日**或根本没有当天条目**
        （老计划可能缺项）→ 休息日；否则训练日。缺项不渲染成空训练日，也不冒充
        「没有计划」——前者会让会话页无从开始，后者会诱导用户重建计划并归档现有计划。
        """
        plan = await self.get_current_plan(user_id)
        if not plan:
            return TodayWorkoutResponse(status="no_plan", is_rest_day=False)

        today_weekday = self._today().isoweekday()  # 1=周一
        today = self._workout_for_weekday(plan, today_weekday)
        if today is None or today.is_rest_day:
            return TodayWorkoutResponse(
                status="rest_day",
                is_rest_day=True,
                day=today.day if today else None,
                focus=today.focus if today else None,
                plan_id=plan.id,
                message=REST_DAY_MESSAGE,
            )

        return TodayWorkoutResponse(
            status="training_day",
            is_rest_day=False,
            day=today.day,
            focus=today.focus,
            exercises=today.exercises,
            estimated_duration=today.estimated_duration,
            exercise_count=len(today.exercises),
            total_sets=sum(exercise.sets for exercise in today.exercises),
            plan_id=plan.id,
        )

    async def generate_plan(
        self,
        user_id: int,
        body_analysis: Optional[dict],
        profile: Optional[dict],
        week_start: datetime.date,
    ) -> TrainingPlanSchema:
        """调用 LLM 生成个性化周训练计划，保存并返回"""
        llm = await self.factory.get_client(user_id=user_id, model_type="chat")
        parser = PydanticOutputParser(pydantic_object=TrainingPlanSchema)

        profile_text = self._format_profile(profile)
        analysis_text = self._format_analysis(body_analysis)

        prompt = (
            f"你是专业健身教练。根据以下信息为用户生成一周（7天）个性化训练计划：\n"
            f"{profile_text}\n{analysis_text}\n\n"
            f"要求：\n"
            f"- 安排 4-5 个训练日，其余为休息日\n"
            f"- 每次训练 45-60 分钟\n"
            f"- 针对弱势肌群重点安排\n"
            f"- 动作数量适中（每日 4-6 个动作）\n"
            f"- user_id 填 {user_id}，week_start 填 {week_start.isoformat()}\n\n"
            f"{parser.get_format_instructions()}"
        )

        response = await observed.invoke(llm, [HumanMessage(content=prompt)])

        try:
            import re
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", response.content.strip())
            cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
            schema = parser.parse(cleaned)
            if cleaned != response.content.strip():
                observed.degraded(llm, reason=observed.DEGRADED_MARKDOWN_WRAPPED)
        except Exception:
            observed.degraded(llm)
            schema = self._default_plan(user_id, week_start)

        # 归档旧计划
        await self._archive_old_plans(user_id)

        # 存库
        db_plan = TrainingPlan(
            user_id=user_id,
            week_start=week_start,
            weekly_plan=[d.model_dump() for d in schema.weekly_plan],
            body_analysis_snapshot=body_analysis,
            difficulty_factor=1.0,
            status="active",
        )
        self.db.add(db_plan)
        await self.db.flush()
        schema.id = db_plan.id
        return schema

    async def adjust_plan_after_workout(
        self, user_id: int, completion_rate: float, difficulty_rating: float
    ) -> Optional[PlanAdjustment]:
        """训练完成后触发动态调整：写回计划，并把「方向 + 理由」落成可查结论。

        返回落盘的结论记录；没有可用计划时返回 None（没有可调整的对象，也就不该
        伪造一条空结论）。
        """
        plan = await self.get_current_plan(user_id)
        if not plan or not plan.id:
            return None

        adjuster = AdjustGraph(user_id=user_id, db=self.db)
        outcome_state = await adjuster.run(
            completion_rate=completion_rate,
            difficulty_rating=difficulty_rating,
            current_plan={"weekly_plan": [d.model_dump() for d in plan.weekly_plan]},
        )

        db_plan = await self.db.get(TrainingPlan, plan.id)
        if db_plan is not None:
            adjusted = outcome_state.get("adjusted_plan") or {}
            db_plan.weekly_plan = adjusted.get("weekly_plan", db_plan.weekly_plan)

        direction = outcome_state.get("adjustment_type") or "keep"
        if direction not in ADJUSTMENT_DIRECTIONS:
            direction = "keep"

        record = PlanAdjustment(
            id=new_adjustment_id(),
            user_id=user_id,
            plan_id=plan.id,
            direction=direction,
            reason=outcome_state.get("reason") or f"完成率 {completion_rate:.0%}，本次未调整训练量",
            completion_rate=completion_rate,
            difficulty_rating=difficulty_rating,
        )
        self.db.add(record)
        if db_plan is not None:
            # 计划侧只存引用：结论的唯一事实源在 plan_adjustments。
            db_plan.latest_adjustment_id = record.id
        await self.db.flush()
        return record

    async def get_latest_adjustment(self, user_id: int) -> Optional[PlanAdjustment]:
        """读取该用户最近一次调整结论；没有记录时返回 None（显式空态）。"""
        result = await self.db.execute(
            select(PlanAdjustment)
            .where(PlanAdjustment.user_id == user_id)
            .order_by(desc(PlanAdjustment.created_at), desc(PlanAdjustment.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_adjustment(
        self, user_id: int, adjustment_id: str
    ) -> Optional[PlanAdjustment]:
        """按稳定标识读取一条调整结论（只限本人）。"""
        result = await self.db.execute(
            select(PlanAdjustment).where(
                PlanAdjustment.id == adjustment_id,
                PlanAdjustment.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _archive_old_plans(self, user_id: int) -> None:
        """将用户旧的 active 计划归档"""
        result = await self.db.execute(
            select(TrainingPlan).where(
                TrainingPlan.user_id == user_id, TrainingPlan.status == "active"
            )
        )
        for plan in result.scalars().all():
            plan.status = "archived"
        await self.db.flush()

    @staticmethod
    def _to_schema(plan: TrainingPlan) -> TrainingPlanSchema:
        """ORM 对象转 Pydantic Schema"""
        return TrainingPlanSchema(
            id=plan.id,
            user_id=plan.user_id,
            week_start=plan.week_start,
            weekly_plan=[DailyWorkout(**d) for d in plan.weekly_plan],
            difficulty_factor=plan.difficulty_factor,
            status=plan.status,
        )

    def _format_profile(self, profile: Optional[dict]) -> str:
        if not profile:
            return "用户档案：未填写"
        return (
            f"用户档案：身高 {profile.get('height', '?')}cm，"
            f"体重 {profile.get('weight', '?')}kg，"
            f"目标 {profile.get('goal', '?')}，"
            f"训练经验 {profile.get('experience', '?')}"
        )

    def _format_analysis(self, analysis: Optional[dict]) -> str:
        if not analysis:
            return "体型分析：未完成"
        return (
            f"体型分析：体型 {analysis.get('body_type', '?')}，"
            f"体脂 {analysis.get('body_fat_range', '?')}，"
            f"弱势肌群 {analysis.get('weak_muscles', [])}，"
            f"优势部位 {analysis.get('strengths', [])}"
        )

    def _default_plan(self, user_id: int, week_start: datetime.date) -> TrainingPlanSchema:
        """LLM 解析失败时的默认基础计划"""
        from app.schemas.plan import Exercise
        default_exercises = [
            Exercise(name="深蹲", sets=3, reps="12", weight_suggestion="体重30%", tips="挺胸收腹"),
            Exercise(
                name="俯卧撑", sets=3, reps="15", weight_suggestion="自重", tips="保持身体平直"
            ),
        ]
        days = []
        for i in range(1, 8):
            is_rest = i in [3, 6, 7]
            days.append(
                DailyWorkout(
                    day=i,
                    focus="全身" if not is_rest else "休息",
                    exercises=[] if is_rest else default_exercises,
                    estimated_duration=0 if is_rest else 45,
                    is_rest_day=is_rest,
                )
            )
        return TrainingPlanSchema(
            user_id=user_id,
            week_start=week_start,
            weekly_plan=days,
        )
