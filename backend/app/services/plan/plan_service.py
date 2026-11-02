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
from app.models.adjustment_job import PlanAdjustmentJob
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord
from app.schemas.plan import (
    DailyWorkout,
    PlanAdjustmentExplanation,
    PlanExplanation,
    PlanGenerationBasis,
    TodayWorkoutResponse,
    TrainingPlanSchema,
)
from app.services.ai import llm_observability as observed
from app.services.ai.adjust_graph import AdjustGraph
from app.services.ai.llm_adjust_analyzers import resolve_llm_context
from app.services.ai.llm_factory import LLMClientFactory

# 休息日提示沿用原接口文案：前端空态与历史文案都依赖它，改文案属于产品决策而非本次契约变更。
REST_DAY_MESSAGE = "今日休息，好好恢复"

# LLM 输入最小化：只取窗口内的聚合统计，原始逐日序列永远不进入 Prompt。
LLM_WEIGHT_WINDOW_DAYS = 30
LLM_TRAINING_WINDOW_DAYS = 7
LLM_BODY_FLAT_EPSILON_KG = 0.1
LLM_AGE_UNDER_18 = "18 岁以下"
LLM_AGE_BANDS: tuple[tuple[int, str], ...] = (
    (18, "18-29"),
    (30, "30-39"),
    (40, "40-49"),
    (50, "50-59"),
    (60, "60 岁及以上"),
)


def _text(value: object) -> Optional[str]:
    """把快照里的自由值收敛成可读文本；非预期类型返回 None 而不是让读取失败。"""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _number(value: object) -> Optional[float]:
    """把档案里的数值收敛成 float；布尔与非法形态返回 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 2)


def _consecutive_days(dates: list[datetime.date]) -> int:
    """从最近一次训练往回数连续天数；日期已去重并升序。"""
    if not dates:
        return 0
    streak = 0
    expected = dates[-1]
    for current in reversed(dates):
        if current == expected:
            streak += 1
            expected = current - datetime.timedelta(days=1)
        else:
            break
    return streak


def _text_list(value: object) -> Optional[list[str]]:
    """列表字段的正常形态是 ``list[str]``；模型偶发写成一个字符串时按单元素兜底。

    解析结果为空（或类型完全无法收敛）时返回 None，让前端走「该行不显示」的降级，
    绝不因为一个字段的形态不合预期就让整份计划读取失败。
    """
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else None
    if isinstance(value, (list, tuple)):
        items = [item for item in (_text(entry) for entry in value) if item]
        return items or None
    return None


class PlanService:
    """训练计划核心服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.factory = LLMClientFactory(db)

    async def _load_current_plan(self, user_id: int) -> Optional[TrainingPlan]:
        """读取用户最新的 active 计划行（读取路径的唯一入口，避免口径分叉）。"""
        result = await self.db.execute(
            select(TrainingPlan)
            .where(TrainingPlan.user_id == user_id, TrainingPlan.status == "active")
            .order_by(desc(TrainingPlan.week_start))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_current_plan(self, user_id: int) -> Optional[TrainingPlanSchema]:
        """获取用户最新的 active 训练计划"""
        plan = await self._load_current_plan(user_id)
        return self._to_schema(plan) if plan else None

    async def get_current_plan_with_explanation(
        self, user_id: int
    ) -> tuple[Optional[TrainingPlanSchema], PlanExplanation]:
        """读取当前计划并附上解释字段（工单 20）。

        解释是纯投影：生成依据来自计划行上的两份快照，调整说明按
        ``latest_adjustment_id`` 读回调整结论记录，不复制文本。旧计划的解释为
        空对象（两个子对象都是 None），读取照常成功。
        """
        plan = await self._load_current_plan(user_id)
        if plan is None:
            return None, PlanExplanation()
        return self._to_schema(plan), await self._build_explanation(plan)

    async def _build_explanation(self, plan: TrainingPlan) -> PlanExplanation:
        return PlanExplanation(
            generation=self._generation_basis(plan),
            latest_adjustment=await self._latest_adjustment_basis(plan),
        )

    @staticmethod
    def _generation_basis(plan: TrainingPlan) -> Optional[PlanGenerationBasis]:
        """把我存的体型快照 + 档案快照投影成对外形状；没有快照时整块为 None。"""
        snapshot = plan.body_analysis_snapshot
        if not isinstance(snapshot, dict) or not snapshot:
            return None
        profile = plan.profile_snapshot if isinstance(plan.profile_snapshot, dict) else None
        return PlanGenerationBasis(
            body_type=_text(snapshot.get("body_type")),
            body_fat_range=_text(snapshot.get("body_fat_range")),
            weak_muscles=_text_list(snapshot.get("weak_muscles")),
            strengths=_text_list(snapshot.get("strengths")),
            analysis_summary=_text(snapshot.get("summary")),
            captured_at=plan.analysis_captured_at,
            profile_goal=_text(profile.get("goal")) if profile else None,
        )

    async def _latest_adjustment_basis(
        self, plan: TrainingPlan
    ) -> Optional[PlanAdjustmentExplanation]:
        """按计划行上的引用读回最近一次调整结论；引用为空或失效时返回 None。"""
        if not plan.latest_adjustment_id:
            return None
        record = await self.get_adjustment(plan.user_id, plan.latest_adjustment_id)
        if record is None:
            return None
        if record.direction not in ADJUSTMENT_DIRECTIONS:
            # 方向是唯一由本系统写入的枚举；越界说明数据已损坏，宁可不解释也不谎报方向。
            return None
        # 前后摘要只在作业的计划差异快照里：打卡反馈读同一行，两处逐字一致。
        job_result = await self.db.execute(
            select(PlanAdjustmentJob)
            .where(PlanAdjustmentJob.adjustment_id == record.id)
            .order_by(desc(PlanAdjustmentJob.created_at))
            .limit(1)
        )
        job = job_result.scalar_one_or_none()
        diff = job.plan_diff if job is not None and isinstance(job.plan_diff, dict) else {}
        return PlanAdjustmentExplanation(
            direction=record.direction,
            trigger="completion_rate",
            completion_rate=record.completion_rate,
            occurred_at=record.created_at,
            reason=record.reason,
            before_summary=_text(diff.get("before_summary")),
            after_summary=_text(diff.get("after_summary")),
        )

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
            # 生成时的档案快照与记下「该次分析被本计划捕获的时刻」：只有存下当时的目标，
            # 读取时才不会拿用户后来改过的档案做错误归因。
            profile_snapshot=profile,
            analysis_captured_at=(
                datetime.datetime.now(datetime.timezone.utc) if body_analysis else None
            ),
            difficulty_factor=1.0,
            status="active",
        )
        self.db.add(db_plan)
        await self.db.flush()
        schema.id = db_plan.id
        return schema

    async def _build_llm_aggregate_summary(
        self, user_id: int, completion_rate: float
    ) -> dict:
        """构造送给模型两维的聚合摘要：只有均值、趋势、计数与训练统计。

        逐日体重序列、用户标识、邮箱、昵称与照片都不在这里出现；Prompt 侧还会
        再做一次白名单过滤，两层共同保证输入最小化。
        """
        profile = await self._load_user_profile(user_id)
        weight = await self._weight_aggregate(user_id)
        training = await self._training_aggregate(user_id, completion_rate)
        return {
            "goal": _text(profile.get("goal")),
            "height_cm": _number(profile.get("height")),
            "weight_kg": _number(profile.get("weight")),
            "age_band": self._age_band(profile.get("age")),
            "weekly_completion_average": training["weekly_completion_average"],
            "completion_sample_count": training["sample_count"],
            "training": {
                "training_days": training["training_days"],
                "consecutive_training_days": training["consecutive_training_days"],
            },
            "weight": weight,
        }

    async def _load_user_profile(self, user_id: int) -> dict:
        """只取档案 JSON；不读取昵称、邮箱、头像等身份字段。"""
        result = await self.db.execute(select(User.profile).where(User.id == user_id))
        profile = result.scalar_one_or_none()
        return profile if isinstance(profile, dict) else {}

    async def _weight_aggregate(self, user_id: int) -> dict:
        """体重窗口聚合：均值、趋势方向与记录条数，不携带逐日原始序列。"""
        since = self._today() - datetime.timedelta(days=LLM_WEIGHT_WINDOW_DAYS)
        result = await self.db.execute(
            select(WeightRecord.weight)
            .where(
                WeightRecord.user_id == user_id,
                WeightRecord.recorded_date >= since,
            )
            .order_by(WeightRecord.recorded_date.asc())
        )
        weights = [float(weight) for weight in result.scalars().all()]
        if not weights:
            return {
                "mean_kg": None,
                "trend_direction": "insufficient",
                "record_count": 0,
                "window_days": LLM_WEIGHT_WINDOW_DAYS,
            }
        change = weights[-1] - weights[0]
        if len(weights) < 2:
            trend = "insufficient"
        elif abs(change) < LLM_BODY_FLAT_EPSILON_KG:
            trend = "flat"
        else:
            trend = "down" if change < 0 else "up"
        return {
            "mean_kg": round(sum(weights) / len(weights), 1),
            "trend_direction": trend,
            "record_count": len(weights),
            "window_days": LLM_WEIGHT_WINDOW_DAYS,
        }

    async def _training_aggregate(
        self, user_id: int, completion_rate: float
    ) -> dict:
        """近 7 天训练聚合：完成率均值、训练天数与连续训练天数。"""
        since = self._today() - datetime.timedelta(days=LLM_TRAINING_WINDOW_DAYS - 1)
        result = await self.db.execute(
            select(WorkoutRecord.workout_date, WorkoutRecord.completion_rate)
            .where(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= since,
            )
            .order_by(WorkoutRecord.workout_date.asc())
        )
        rows = list(result.all())
        dates = sorted({row.workout_date for row in rows if row.workout_date})
        rates = [
            float(row.completion_rate)
            for row in rows
            if isinstance(row.completion_rate, (int, float))
        ]
        weekly_average = (
            round(sum(rates) / len(rates), 3) if rates else round(float(completion_rate), 3)
        )
        return {
            "weekly_completion_average": weekly_average,
            "sample_count": len(rates),
            "training_days": len(dates),
            "consecutive_training_days": _consecutive_days(dates),
        }

    @staticmethod
    def _age_band(age: object) -> Optional[str]:
        """只下送年龄段，不下送精确年龄。"""
        if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
            return None
        if age < LLM_AGE_BANDS[0][0]:
            return LLM_AGE_UNDER_18
        band = LLM_AGE_BANDS[0][1]
        for threshold, label in LLM_AGE_BANDS:
            if age >= threshold:
                band = label
        return band

    async def adjust_plan_after_workout(
        self,
        user_id: int,
        completion_rate: float,
        difficulty_rating: Optional[float],
        *,
        fatigue_scores: Optional[list[int]] = None,
        sleep_hours: Optional[float] = None,
        sleep_quality: Optional[int] = None,
    ) -> Optional[PlanAdjustment]:
        """训练完成后触发动态调整：五维评估 → 合并决策 → 写回计划并落成可查结论。

        返回落盘的结论记录；没有可用计划时返回 None（没有可调整的对象，也就不该
        伪造一条空结论）。

        疲劳 / 睡眠目前没有打卡字段，缺省值由分析器自己补齐；只有调用方真的提供了
        这两类输入时才传给 Graph，保持 ``AdjustGraph`` 的既有调用契约向后兼容。
        """
        plan = await self.get_current_plan(user_id)
        if not plan or not plan.id:
            return None

        summary = await self._build_llm_aggregate_summary(user_id, completion_rate)
        llm_context = await resolve_llm_context(
            self.factory, user_id, summary=summary
        )
        adjuster = AdjustGraph(user_id=user_id, db=self.db)
        # 兼容既有替身：运行上下文以属性注入，不改变 run() 的既有调用契约。
        adjuster.llm_context = llm_context
        run_kwargs: dict[str, object] = {
            "completion_rate": completion_rate,
            "difficulty_rating": difficulty_rating,
            "current_plan": {
                "weekly_plan": [d.model_dump() for d in plan.weekly_plan],
                "difficulty_factor": plan.difficulty_factor,
            },
        }
        if fatigue_scores or sleep_hours is not None or sleep_quality is not None:
            run_kwargs.update(
                fatigue_scores=fatigue_scores,
                sleep_hours=sleep_hours,
                sleep_quality=sleep_quality,
            )
        outcome_state = await adjuster.run(**run_kwargs)

        db_plan = await self.db.get(TrainingPlan, plan.id)
        if db_plan is not None:
            adjusted = outcome_state.get("adjusted_plan") or {}
            db_plan.weekly_plan = adjusted.get("weekly_plan", db_plan.weekly_plan)
            db_plan.difficulty_factor = adjusted.get(
                "difficulty_factor", db_plan.difficulty_factor
            )

        direction = outcome_state.get("adjustment_type") or "keep"
        if direction not in ADJUSTMENT_DIRECTIONS:
            direction = "keep"

        # 工单 24：五维明细与合并小结追加进同一条结论记录，不新建并行存储。
        merged = outcome_state.get("merged") or {}
        reason = (
            outcome_state.get("reason") or f"完成率 {completion_rate:.0%}，本次未调整训练量"
        )[:255]
        record = PlanAdjustment(
            id=new_adjustment_id(),
            user_id=user_id,
            plan_id=plan.id,
            direction=direction,
            reason=reason,
            completion_rate=completion_rate,
            difficulty_rating=difficulty_rating,
            overall_score=merged.get("overall_score"),
            delta_percent=outcome_state.get("delta_percent"),
            dimensions=outcome_state.get("dimensions") or None,
            merged=merged or None,
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
