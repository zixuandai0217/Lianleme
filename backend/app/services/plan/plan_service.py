"""
PlanService：训练计划存取、AI 生成计划、今日任务获取、周视图查询
"""
import datetime
import json
from typing import Optional

from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import TrainingPlan
from app.schemas.plan import DailyWorkout, TrainingPlanSchema
from app.services.ai.llm_factory import LLMClientFactory
from app.services.ai.adjust_graph import AdjustGraph


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

    async def get_today_workout(self, user_id: int) -> Optional[dict]:
        """获取今日训练任务（根据周几匹配）"""
        plan = await self.get_current_plan(user_id)
        if not plan:
            return None
        today_weekday = datetime.date.today().isoweekday()  # 1=周一
        for day in plan.weekly_plan:
            if day.day == today_weekday:
                if day.is_rest_day:
                    return None
                return day.model_dump()
        return None

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

        response = await llm.ainvoke([HumanMessage(content=prompt)])

        try:
            schema = parser.parse(response.content)
        except Exception:
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
    ) -> None:
        """训练完成后触发动态调整，更新当前计划"""
        plan = await self.get_current_plan(user_id)
        if not plan or not plan.id:
            return
        adjuster = AdjustGraph(user_id=user_id, db=self.db)
        adjusted = await adjuster.run(
            completion_rate=completion_rate,
            difficulty_rating=difficulty_rating,
            current_plan={"weekly_plan": [d.model_dump() for d in plan.weekly_plan]},
        )
        result = await self.db.execute(
            select(TrainingPlan).where(TrainingPlan.id == plan.id)
        )
        db_plan = result.scalar_one_or_none()
        if db_plan:
            db_plan.weekly_plan = adjusted.get("weekly_plan", db_plan.weekly_plan)
            await self.db.flush()

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

    def _to_schema(self, plan: TrainingPlan) -> TrainingPlanSchema:
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
            Exercise(name="俯卧撑", sets=3, reps="15", weight_suggestion="自重", tips="保持身体平直"),
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
