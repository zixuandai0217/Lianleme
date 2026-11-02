"""训练会话服务：开始 / 完成一组 / 跳过 / 恢复读取（工单 22）。

会话进度以「动作序号 + 组序号」定位：完成一组是集合式操作，重复提交同一组不会重复
计数，也不接受进度回退；跳过动作把动作标记为 skipped 并留在明细里，不计入完成组数。
派生视图（当前动作、组内进度、下一个动作、可打卡状态）在这里统一计算，前端不推算。
"""
import copy
import datetime
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.local_time import local_date, local_now
from app.models.workout_session import (
    SESSION_IDLE_HOURS,
    SESSION_STATUS_ABANDONED,
    SESSION_STATUS_IN_PROGRESS,
    WorkoutSession,
    new_session_id,
)
from app.schemas.workout_session import (
    SessionExerciseView,
    SessionProgress,
    WorkoutSessionView,
)
from app.services.plan.plan_service import PlanService

# 稳定错误码 -> HTTP 状态；路由层只做映射，不重复判断业务语义。
ERROR_STATUS: dict[str, int] = {
    "no_plan": 409,
    "rest_day": 409,
    "session_not_found": 404,
    "session_finished": 409,
    "exercise_not_found": 422,
    "exercise_skipped": 409,
    "exercise_completed": 409,
    "set_out_of_range": 422,
    "set_out_of_order": 422,
}


class SessionError(Exception):
    """可映射成稳定 HTTP 错误的业务失败。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _PlanExercise:
    name: str
    sets: int
    reps: str
    weight_suggestion: str
    tips: str
    rest_seconds: int


class WorkoutSessionService:
    """当日训练会话的推进与读取。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- clock ----------
    @staticmethod
    def _today() -> datetime.date:
        """The user-facing local date (single source of truth for "today")."""
        return local_date()

    # ---------- start / read ----------
    async def start(self, user_id: int) -> WorkoutSession:
        """开始当天训练；同日重复调用返回已存在的会话，休息日/无计划则拒绝。"""
        existing = await self.current(user_id)
        if existing is not None:
            return existing

        plans = PlanService(self.db)
        plan = await plans.get_current_plan(user_id)
        if plan is None:
            raise SessionError("no_plan", "还没有训练计划，先生成一份本周计划")

        today = self._today()
        workout = PlanService._workout_for_weekday(plan, today.isoweekday())
        if workout is None or workout.is_rest_day:
            raise SessionError("rest_day", "今天是休息日，休息也是训练的一部分")

        exercises = [
            {
                "order": order,
                "name": exercise.name,
                "sets": exercise.sets,
                "reps": exercise.reps,
                "weight_suggestion": exercise.weight_suggestion,
                "tips": exercise.tips,
                "rest_seconds": exercise.rest_seconds,
                "completed_sets": 0,
                "skipped": False,
                "skip_reason": None,
            }
            for order, exercise in enumerate(workout.exercises, start=1)
        ]
        total_sets = sum(item["sets"] for item in exercises)

        session = WorkoutSession(
            id=new_session_id(),
            user_id=user_id,
            plan_id=plan.id,
            session_date=today,
            status=SESSION_STATUS_IN_PROGRESS,
            total_sets=total_sets,
            completed_sets=0,
            exercises=exercises,
        )
        self.db.add(session)
        try:
            await self.db.flush()
        except IntegrityError:
            # 并发双击「开始训练」：唯一键兜底，回滚本次插入后返回已存在的那一条。
            await self.db.rollback()
            raced = await self.current(user_id)
            if raced is None:  # pragma: no cover - 唯一键冲突必然有另一条
                raise
            return raced
        return session

    async def get(self, session_id: str) -> WorkoutSession | None:
        return await self.db.get(WorkoutSession, session_id)

    async def current(self, user_id: int) -> WorkoutSession | None:
        """The session the client should resume.

        An in-progress session wins even when it started before midnight (training
        continued past 00:00 still belongs to its start date); once it has been idle
        for ``SESSION_IDLE_HOURS`` it converges to abandoned on read, and today's
        (possibly completed) session is returned read-only instead.
        """
        result = await self.db.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status == SESSION_STATUS_IN_PROGRESS,
            )
            .order_by(WorkoutSession.session_date.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if session is not None:
            if self._idle_hours(session) >= SESSION_IDLE_HOURS:
                # 12 小时无活动：状态机收敛为 abandoned，同一天再次进入只读回看。
                await self.abandon(session)
            else:
                return session

        today_result = await self.db.execute(
            select(WorkoutSession).where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.session_date == self._today(),
            )
        )
        return today_result.scalar_one_or_none()

    @staticmethod
    def _idle_hours(session: WorkoutSession) -> float:
        last = session.last_activity_at
        if last is None:
            return 0.0
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.timezone.utc)
        now = local_now().astimezone(datetime.timezone.utc)
        return max(0.0, (now - last).total_seconds() / 3600)

    # ---------- progress ----------
    async def complete_set(
        self, session_id: str, exercise_index: int, set_index: int
    ) -> WorkoutSession:
        """完成一组；同一组重复提交幂等，不回退进度。"""
        session = await self._require_in_progress(session_id)
        # 深拷贝后再整体赋回：JSONB 列是可变对象，原地修改不会被 SQLAlchemy 识别为变更。
        exercises = copy.deepcopy(session.exercises or [])
        if exercise_index >= len(exercises):
            raise SessionError("exercise_not_found", "没有这个动作")
        exercise = exercises[exercise_index]
        if exercise["skipped"]:
            raise SessionError("exercise_skipped", "这个动作已经跳过")
        if set_index >= exercise["sets"]:
            raise SessionError("set_out_of_range", "组序号超出计划组数")

        completed = int(exercise["completed_sets"])
        if set_index < completed:
            return session  # 幂等：重复提交已完成的组不改变任何状态
        if set_index > completed:
            raise SessionError("set_out_of_order", "请按顺序完成组数，不能跳过中间组")

        exercise["completed_sets"] = completed + 1
        session.completed_sets += 1
        session.exercises = exercises
        session.last_activity_at = local_now().astimezone(datetime.timezone.utc)
        await self.db.flush()
        return session

    async def skip_exercise(
        self, session_id: str, exercise_index: int, reason: str
    ) -> WorkoutSession:
        """跳过动作（必须带原因）；已跳过的重复提交幂等。"""
        session = await self._require_in_progress(session_id)
        # 深拷贝后再整体赋回：JSONB 列是可变对象，原地修改不会被 SQLAlchemy 识别为变更。
        exercises = copy.deepcopy(session.exercises or [])
        if exercise_index >= len(exercises):
            raise SessionError("exercise_not_found", "没有这个动作")
        exercise = exercises[exercise_index]
        if exercise["skipped"]:
            return session
        if int(exercise["completed_sets"]) >= int(exercise["sets"]):
            raise SessionError("exercise_completed", "这个动作已经完成，不能跳过")

        exercise["skipped"] = True
        exercise["skip_reason"] = reason.strip()
        session.exercises = exercises
        session.last_activity_at = local_now().astimezone(datetime.timezone.utc)
        await self.db.flush()
        return session

    # ---------- view ----------
    def view(self, session: WorkoutSession) -> WorkoutSessionView:
        """Project the stored session into the resumable, server-computed view."""
        exercises = [
            self._exercise_view(index, item)
            for index, item in enumerate(session.exercises or [])
        ]
        pending = [item for item in exercises if item.status == "pending"]
        current = pending[0] if pending else None
        next_exercise = pending[1] if len(pending) > 1 else None
        finished = not pending
        total = session.total_sets or sum(item.sets for item in exercises)
        percent = round((session.completed_sets / total) * 100) if total else 0

        return WorkoutSessionView(
            session_id=session.id,
            user_id=session.user_id,
            plan_id=session.plan_id,
            status=session.status,
            session_date=session.session_date,
            started_at=session.started_at,
            last_activity_at=session.last_activity_at,
            progress=SessionProgress(
                completed_sets=session.completed_sets, total_sets=total, percent=percent
            ),
            exercises=exercises,
            current_exercise=current,
            next_exercise=next_exercise,
            finished=finished,
            can_checkin=finished and session.status == SESSION_STATUS_IN_PROGRESS,
        )

    @staticmethod
    def _exercise_view(index: int, item: dict) -> SessionExerciseView:
        completed = int(item.get("completed_sets", 0))
        sets = int(item.get("sets", 0))
        skipped = bool(item.get("skipped"))
        if skipped:
            status = "skipped"
        elif completed >= sets:
            status = "completed"
        else:
            status = "pending"
        target = completed + 1 if status == "pending" else None
        return SessionExerciseView(
            index=index,
            order=int(item.get("order", index + 1)),
            name=str(item.get("name", "")),
            sets=sets,
            reps=str(item.get("reps", "")),
            weight_suggestion=str(item.get("weight_suggestion", "")),
            tips=str(item.get("tips", "")),
            rest_seconds=int(item.get("rest_seconds", 60)),
            completed_sets=completed,
            skipped=skipped,
            skip_reason=item.get("skip_reason"),
            status=status,
            target_set_number=target,
        )

    # ---------- helpers ----------
    async def _require_in_progress(self, session_id: str) -> WorkoutSession:
        session = await self.get(session_id)
        if session is None:
            raise SessionError("session_not_found", "找不到这次训练会话")
        if session.status != SESSION_STATUS_IN_PROGRESS:
            raise SessionError("session_finished", "这次训练已经结束，不能再修改")
        return session

    async def abandon(self, session: WorkoutSession) -> WorkoutSession:
        session.status = SESSION_STATUS_ABANDONED
        session.ended_at = local_now().astimezone(datetime.timezone.utc)
        session.last_activity_at = session.ended_at
        await self.db.flush()
        return session
