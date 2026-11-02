"""陪练的确定性规划环节：快捷动作 + 教练状态。

本模块是纯规则实现，不调用模型、不读取随机数：相同训练上下文与相同用户消息
永远得到相同的动作列表与状态。路由只负责把上下文准备好，再把规划结果转成
``actions`` / ``state`` 帧并随助手消息一起持久化。

快捷动作拆成「按钮文案 label」与「点击后发送的文本 prompt」：按钮可以很短，
发出去的消息仍然是一句完整的话。上下文取不到时回落到与训练无关的通用动作集，
按钮区永远不空。
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.schemas.chat import CoachAction, CoachStateName

logger = logging.getLogger(__name__)

STATUS_TRAINING_DAY = "training_day"
STATUS_REST_DAY = "rest_day"
STATUS_NO_PLAN = "no_plan"
STATUS_UNKNOWN = "unknown"

CoachContextStatus = Literal["training_day", "rest_day", "no_plan", "unknown"]

# 通用动作集：与旧页面写死的四条等价，是上下文缺失时的降级路径。
GENERIC_ACTIONS: tuple[CoachAction, ...] = (
    CoachAction(label="帮我安排热身", prompt="根据今天的计划，帮我安排热身"),
    CoachAction(label="动作注意什么", prompt="第一个动作应该注意什么？"),
    CoachAction(label="状态一般", prompt="今天状态一般，训练怎么调整？"),
    CoachAction(label="开练提醒", prompt="给我一句开练前的提醒"),
)

# 用户消息里的确定性关键词：只影响状态推导，不影响动作集合。
_SET_DONE_HINTS = ("做完", "完成", "干完", "搞完", "打卡")
_LAST_SET_HINTS = ("最后一组", "最后这组", "收尾组")
_SET_ACTIVE_HINTS = ("开始", "正在", "这组", "第", "准备做", "下一组", "做组")
_REST_HINTS = ("休息", "歇", "喘")
_COMPLETE_HINTS = ("全部练完", "全部完成", "训练结束", "练完了", "收工")


@dataclass(frozen=True)
class CoachContext:
    """服务端能确定的训练上下文快照。

    组数同时保留「当前动作的组进度」与「整场会话进度」：前者决定动作文案，
    后者用于判断最后一组与完成态。字段缺失一律降级为 0 / None，规划器不抛错。
    """

    status: CoachContextStatus = STATUS_UNKNOWN
    current_exercise: str | None = None
    exercise_completed_sets: int = 0
    exercise_total_sets: int = 0
    session_completed_sets: int = 0
    session_total_sets: int = 0
    rest_seconds: int = 60
    finished: bool = False
    plan_id: int | None = None

    @classmethod
    def from_request(cls, context: Mapping[str, object] | None) -> "CoachContext":
        """Build a best-effort context from a request payload or a plain mapping.

        This is the fallback used when today's plan / session cannot be read; it
        never raises, so a broken context cannot break a coach turn. It also
        accepts the planner's own field names, which keeps direct callers honest.
        """
        values = context or {}
        status = values.get("status")
        if status in (STATUS_TRAINING_DAY, STATUS_REST_DAY, STATUS_NO_PLAN):
            parsed_status: CoachContextStatus = status  # type: ignore[assignment]
        elif values.get("is_rest_day") is True:
            parsed_status = STATUS_REST_DAY
        else:
            parsed_status = STATUS_UNKNOWN

        exercise = _text(values.get("current_exercise"))
        completed = _non_negative_int(values.get("completed_sets"))
        total = _non_negative_int(values.get("total_sets"))
        exercise_completed = _non_negative_int(
            values.get("exercise_completed_sets", completed)
        )
        exercise_total = _non_negative_int(values.get("exercise_total_sets", total))
        session_completed = _non_negative_int(
            values.get("session_completed_sets", completed)
        )
        session_total = _non_negative_int(values.get("session_total_sets", total))

        if parsed_status == STATUS_UNKNOWN:
            if exercise is None and total == 0:
                return cls()
            parsed_status = STATUS_TRAINING_DAY

        return cls(
            status=parsed_status,
            current_exercise=exercise,
            exercise_completed_sets=min(exercise_completed, exercise_total)
            if exercise_total
            else exercise_completed,
            exercise_total_sets=exercise_total,
            session_completed_sets=session_completed,
            session_total_sets=session_total,
            rest_seconds=_positive_int(values.get("rest_seconds", 60), 60),
            finished=values.get("finished") is True,
            plan_id=_optional_int(values.get("plan_id")),
        )


@dataclass(frozen=True)
class CoachTurnPlan:
    """一轮对话的动作与状态；两者都由规划器一次性算出。"""

    coach_state: CoachStateName
    actions: list[CoachAction]


ContextInput = CoachContext | Mapping[str, object]


def _coerce_context(context: ContextInput | None) -> CoachContext:
    """Accept the planner's dataclass or a plain mapping without raising."""
    if isinstance(context, CoachContext):
        return context
    return CoachContext.from_request(context)


async def resolve_coach_context(
    db: object,
    user_id: int,
    request_context: Mapping[str, object] | None = None,
) -> CoachContext:
    """Read today's plan + workout session, falling back to the request payload.

    Context resolution is deliberately fail-open: a database hiccup must not turn
    into a failed coach turn. The fallback still gives a non-empty action set.
    """
    # 延迟导入：plan / workout 服务会间接导入 AI 服务，放在模块顶层会形成环。
    from app.services.plan.plan_service import PlanService
    from app.services.workout.session_service import WorkoutSessionService

    fallback = CoachContext.from_request(request_context)
    try:
        today = await PlanService(db).get_today_state(user_id)
        session = await WorkoutSessionService(db).current(user_id)
    except Exception:
        logger.debug("陪练上下文读取失败，回落到请求上下文", exc_info=True)
        return fallback

    status = getattr(today, "status", STATUS_UNKNOWN)
    if status == STATUS_NO_PLAN:
        return CoachContext(status=STATUS_NO_PLAN)
    if status == STATUS_REST_DAY:
        return CoachContext(
            status=STATUS_REST_DAY,
            session_total_sets=_non_negative_int(getattr(today, "total_sets", 0)),
            plan_id=_optional_int(getattr(today, "plan_id", None)),
        )
    if status != STATUS_TRAINING_DAY:
        return fallback

    view = WorkoutSessionService(db).view(session) if session is not None else None
    current = getattr(view, "current_exercise", None) if view is not None else None
    exercises = getattr(today, "exercises", None) or []
    payload_name = fallback.current_exercise

    current_name: str | None = None
    exercise_completed = 0
    exercise_total = 0
    rest_seconds = 60
    finished = bool(getattr(view, "finished", False)) if view is not None else False

    if current is not None:
        current_name = _text(getattr(current, "name", None))
        exercise_completed = _non_negative_int(getattr(current, "completed_sets", 0))
        exercise_total = _non_negative_int(getattr(current, "sets", 0))
        rest_seconds = _positive_int(getattr(current, "rest_seconds", 60), 60)
    else:
        chosen = next(
            (exercise for exercise in exercises if getattr(exercise, "name", None) == payload_name),
            exercises[0] if exercises else None,
        )
        if chosen is not None:
            current_name = _text(getattr(chosen, "name", None))
            exercise_total = _non_negative_int(getattr(chosen, "sets", 0))
            rest_seconds = _positive_int(getattr(chosen, "rest_seconds", 60), 60)
            if payload_name == current_name:
                exercise_completed = min(fallback.exercise_completed_sets, exercise_total)
        else:
            current_name = payload_name
            exercise_completed = fallback.exercise_completed_sets
            exercise_total = fallback.exercise_total_sets
            rest_seconds = fallback.rest_seconds

    progress = getattr(view, "progress", None) if view is not None else None
    session_completed = (
        _non_negative_int(getattr(progress, "completed_sets", 0))
        if progress is not None
        else 0
    )
    session_total = (
        _non_negative_int(getattr(progress, "total_sets", 0))
        if progress is not None
        else _non_negative_int(getattr(today, "total_sets", 0))
    )

    return CoachContext(
        status=STATUS_TRAINING_DAY,
        current_exercise=current_name,
        exercise_completed_sets=exercise_completed,
        exercise_total_sets=exercise_total,
        session_completed_sets=session_completed,
        session_total_sets=session_total,
        rest_seconds=rest_seconds,
        finished=finished,
        plan_id=_optional_int(getattr(today, "plan_id", None)),
    )


def plan_quick_actions(context: ContextInput) -> list[CoachAction]:
    """Return 1–4 deterministic quick actions for one training context.

    Contextual progress, rest day, no-plan and unresolved contexts each get a
    distinct set. The generic set is the last-resort fallback and is never empty.
    """
    context = _coerce_context(context)
    if context.status == STATUS_TRAINING_DAY:
        return _training_day_actions(context)
    if context.status == STATUS_REST_DAY:
        return _rest_day_actions()
    if context.status == STATUS_NO_PLAN:
        return _no_plan_actions()
    return list(GENERIC_ACTIONS)


def derive_coach_state(context: ContextInput, message: str) -> CoachStateName:
    """Derive one of guide / count / rest / complete from context and message.

    The model never supplies this value: a missed state sentence must not leave
    the digital coach stuck on the wrong expression. Defaults to ``guide``.
    """
    context = _coerce_context(context)
    text = (message or "").strip()
    has_current = bool(context.current_exercise)
    exercise_total = context.exercise_total_sets

    if context.finished:
        return "complete"
    if exercise_total > 0 and context.exercise_completed_sets >= exercise_total:
        return "complete"
    if any(hint in text for hint in _COMPLETE_HINTS):
        return "complete"
    if any(hint in text for hint in _SET_DONE_HINTS):
        if any(hint in text for hint in _LAST_SET_HINTS):
            return "complete"
        return "rest" if has_current else "guide"
    if has_current and any(hint in text for hint in _SET_ACTIVE_HINTS):
        return "count"
    if has_current and any(hint in text for hint in _REST_HINTS):
        return "rest"
    return "guide"


def plan_coach_turn(context: ContextInput, message: str) -> CoachTurnPlan:
    """Compute a turn's actions and state, degrading instead of failing."""
    context = _coerce_context(context)
    try:
        state = derive_coach_state(context, message)
    except Exception:
        logger.exception("教练状态推导失败，回落 guide")
        state = "guide"

    try:
        actions = plan_quick_actions(context)
    except Exception:
        logger.exception("快捷动作规划失败，回落通用动作")
        actions = list(GENERIC_ACTIONS)

    if not actions:
        actions = list(GENERIC_ACTIONS)
    return CoachTurnPlan(coach_state=state, actions=actions[:4])


def _training_day_actions(context: CoachContext) -> list[CoachAction]:
    """Actions tied to the current exercise and its set progress."""
    exercise = (context.current_exercise or "当前动作").strip()
    total = context.exercise_total_sets
    completed = context.exercise_completed_sets

    if context.finished or (total > 0 and completed >= total):
        return [
            CoachAction(label="今天总结", prompt="帮我总结一下今天的训练表现"),
            CoachAction(label="拉伸放松", prompt="训练完了，带我做一些拉伸放松"),
            CoachAction(label="补充营养", prompt="练完这一轮，饮食和补剂怎么安排？"),
            CoachAction(label="明天计划", prompt="明天的训练安排是什么？"),
        ]

    next_set = max(1, completed + 1)
    if total > 0:
        next_set = min(next_set, total)
    return [
        CoachAction(
            label="完成这组",
            prompt=f"我完成了{exercise}第{next_set}组",
        ),
        CoachAction(
            label="动作要领",
            prompt=f"{exercise}的动作要领是什么？",
        ),
        CoachAction(
            label="换动作",
            prompt=f"{exercise}这组做完换什么动作？",
        ),
        CoachAction(
            label="状态一般",
            prompt=f"今天状态一般，{exercise}的强度怎么调整？",
        ),
    ]


def _rest_day_actions() -> list[CoachAction]:
    """Recovery-day actions; no current exercise exists to anchor on."""
    return [
        CoachAction(label="恢复建议", prompt="今天是恢复日，给我一些恢复建议"),
        CoachAction(label="拉伸动作", prompt="推荐几个今天能做的拉伸动作"),
        CoachAction(label="明天安排", prompt="明天的训练安排是什么？"),
        CoachAction(label="恢复饮食", prompt="恢复日饮食上要注意什么？"),
    ]


def _no_plan_actions() -> list[CoachAction]:
    """No active plan: actions that help the user get to a plan."""
    return [
        CoachAction(label="制定计划", prompt="帮我制定一份本周训练计划"),
        CoachAction(label="今天练什么", prompt="还没有训练计划，今天可以先练什么？"),
        CoachAction(label="热身建议", prompt="先带我做个热身吧"),
        CoachAction(label="动作入门", prompt="新手先练哪些动作比较稳？"),
    ]


def _text(value: object) -> str | None:
    """Normalize an optional human-readable field; blank becomes None."""
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _non_negative_int(value: object) -> int:
    """Parse an optional counter without ever raising or returning a negative."""
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _positive_int(value: object, default: int) -> int:
    """Parse an optional positive integer, falling back to the default."""
    parsed = _non_negative_int(value)
    return parsed or default


def _optional_int(value: object) -> int | None:
    """Parse an optional integer identifier."""
    if value is None:
        return None
    parsed = _non_negative_int(value)
    return parsed or None
