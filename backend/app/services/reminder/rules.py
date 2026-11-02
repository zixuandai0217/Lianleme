"""提醒规则（工单 34）：六条规则 + 优先级 + 免打扰时段判定。

规则是纯函数：输入「本地时刻 + 今日事实 + 用户偏好」，输出候选提醒或被拒绝的原因。
它不碰数据库、不读系统时钟，因此每条规则都能脱离环境单测；调度与投递链路只负责
把「查出来的事实」喂进来，并把「跳过」落成可查记录。
"""
import datetime
from dataclasses import dataclass, field

from app.models.reminder_preference import (
    DEFAULT_DAILY_CAP,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_WEEKLY_GOAL_TARGET,
)

RULE_DAILY_TRAINING = "daily_training"
RULE_REST_DAY_NOTE = "rest_day_note"
RULE_RECALL_INACTIVE = "recall_inactive"
RULE_WEEKLY_GOAL_HIT = "weekly_goal_hit"
RULE_WEEKLY_GOAL_GAP = "weekly_goal_gap"
RULE_ONBOARDING_NUDGE = "onboarding_nudge"

# 同日命中多条时的裁剪顺序：召回 > 每日训练 > 周目标 > 引导（数字小优先）。
RULE_PRIORITY = {
    RULE_RECALL_INACTIVE: 0,
    RULE_DAILY_TRAINING: 1,
    RULE_REST_DAY_NOTE: 2,
    RULE_WEEKLY_GOAL_HIT: 3,
    RULE_WEEKLY_GOAL_GAP: 3,
    RULE_ONBOARDING_NUDGE: 4,
}

DEFAULT_REMINDER_HOUR = 19
# 每条每日提醒的当日有效窗口（小时）；超出窗口不跨日补发。
DAILY_WINDOW_HOURS = 4

# 召回阶梯：第 3、7 天各一次；14 天起每 7 天一次节奏上限。
RECALL_FIRST_DAYS = 3
RECALL_SECOND_DAYS = 7
RECALL_SLOWDOWN_DAYS = 14
RECALL_SLOW_INTERVAL_DAYS = 7

# 跳过的原因（写进投递记录，供运营回答「他今天为什么没收到」）。
SKIP_DISABLED = "disabled_by_preference"
SKIP_OUTSIDE_WINDOW = "outside_daily_window"
SKIP_QUIET_HOURS = "quiet_hours"
SKIP_DAILY_CAP = "daily_cap"
SKIP_ALREADY_THIS_WEEK = "already_sent_this_week"
SKIP_ALREADY_REMINDED_TODAY = "already_reminded_today"
SKIP_ONBOARDING_EXHAUSTED = "onboarding_exhausted"


@dataclass(frozen=True)
class ReminderCandidate:
    """一条待投递的提醒（渲染参数在 ``params`` 里，正文已渲染）。"""

    rule_code: str
    title: str
    body: str
    target_path: str
    params: dict = field(default_factory=dict)

    @property
    def priority(self) -> int:
        return RULE_PRIORITY.get(self.rule_code, len(RULE_PRIORITY))


@dataclass(frozen=True)
class ReminderPreferences:
    """规则判定需要的用户偏好（与 ORM 解耦，便于单测）。"""

    daily_training_enabled: bool = True
    rest_day_note_enabled: bool = False
    recall_inactive_enabled: bool = True
    weekly_goal_enabled: bool = True
    onboarding_nudge_enabled: bool = True
    quiet_hours_start: str = DEFAULT_QUIET_HOURS_START
    quiet_hours_end: str = DEFAULT_QUIET_HOURS_END
    daily_cap: int = DEFAULT_DAILY_CAP
    weekly_goal_target: int = DEFAULT_WEEKLY_GOAL_TARGET


@dataclass(frozen=True)
class ReminderContext:
    """一次 tick 里某个用户的今日事实（由服务层查库后传入）。"""

    now_local: datetime.datetime
    is_training_day: bool = False
    has_checked_in_today: bool = False
    focus: str | None = None
    estimated_duration: int | None = None
    last_checkin_date: datetime.date | None = None
    week_checkins: int = 0
    has_plan: bool = False
    has_body_analysis: bool = False
    registered_days_ago: int = 0
    onboarding_nudges_sent: int = 0
    reminders_sent_today: int = 0
    rules_sent_this_week: frozenset[str] = frozenset()
    reminder_hour: int = DEFAULT_REMINDER_HOUR

    @property
    def weekday(self) -> int:
        return self.now_local.isoweekday()


@dataclass(frozen=True)
class RuleOutcome:
    """一条规则的判定结果：要么是可投递候选，要么是一个可查的跳过原因。"""

    rule_code: str
    candidate: ReminderCandidate | None = None
    skip_reason: str | None = None


def parse_hhmm(value: str) -> datetime.time:
    """Parse ``HH:MM``; raises ValueError for anything else."""
    hour, minute = value.split(":")
    return datetime.time(int(hour), int(minute))


def quiet_hours_span(prefs: ReminderPreferences) -> tuple[datetime.time, datetime.time]:
    """The quiet window; the API rejects start == end, so malformed rows mean "no quiet hours"."""
    return parse_hhmm(prefs.quiet_hours_start), parse_hhmm(prefs.quiet_hours_end)


def in_quiet_hours(prefs: ReminderPreferences, moment: datetime.time) -> bool:
    """Whether ``moment`` is inside the quiet window (supports crossing midnight)."""
    start, end = quiet_hours_span(prefs)
    if start == end:
        return False
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def daily_window(
    now_local: datetime.datetime, reminder_hour: int
) -> tuple[datetime.datetime, datetime.datetime]:
    """The daily delivery window for a reminder hour (same local day)."""
    start = now_local.replace(hour=reminder_hour, minute=0, second=0, microsecond=0)
    return start, start + datetime.timedelta(hours=DAILY_WINDOW_HOURS)


def window_state(now_local: datetime.datetime, reminder_hour: int) -> str:
    """``before`` (not due yet) / ``inside`` (deliver now) / ``after`` (window closed)."""
    start, end = daily_window(now_local, reminder_hour)
    if now_local < start:
        return "before"
    if now_local >= end:
        return "after"
    return "inside"


def week_start_of(day: datetime.date) -> datetime.date:
    """ISO week start (Monday) containing ``day``."""
    return day - datetime.timedelta(days=day.weekday())


# ---------------------------------------------------------------- rules


def _daily_training(ctx: ReminderContext, prefs: ReminderPreferences) -> RuleOutcome:
    if not prefs.daily_training_enabled:
        return RuleOutcome(RULE_DAILY_TRAINING, skip_reason=SKIP_DISABLED)
    if not ctx.is_training_day or ctx.has_checked_in_today:
        return RuleOutcome(RULE_DAILY_TRAINING)
    state = window_state(ctx.now_local, ctx.reminder_hour)
    if state == "before":
        return RuleOutcome(RULE_DAILY_TRAINING)
    if state == "after":
        return RuleOutcome(RULE_DAILY_TRAINING, skip_reason=SKIP_OUTSIDE_WINDOW)

    focus = ctx.focus or "今日训练"
    body = f"{focus}还没练，练完记得打卡。"
    if ctx.estimated_duration:
        body = f"{focus}约 {ctx.estimated_duration} 分钟，练完记得打卡。"
    return RuleOutcome(
        RULE_DAILY_TRAINING,
        candidate=ReminderCandidate(
            rule_code=RULE_DAILY_TRAINING,
            title="今天的训练还没打卡",
            body=body,
            target_path="/",
            params={
                "focus": ctx.focus,
                "estimated_duration": ctx.estimated_duration,
                "reminder_hour": ctx.reminder_hour,
            },
        ),
    )


def _rest_day_note(ctx: ReminderContext, prefs: ReminderPreferences) -> RuleOutcome:
    if not prefs.rest_day_note_enabled:
        return RuleOutcome(RULE_REST_DAY_NOTE, skip_reason=SKIP_DISABLED)
    if not ctx.has_plan or ctx.is_training_day:
        return RuleOutcome(RULE_REST_DAY_NOTE)
    state = window_state(ctx.now_local, ctx.reminder_hour)
    if state == "before":
        return RuleOutcome(RULE_REST_DAY_NOTE)
    if state == "after":
        return RuleOutcome(RULE_REST_DAY_NOTE, skip_reason=SKIP_OUTSIDE_WINDOW)
    return RuleOutcome(
        RULE_REST_DAY_NOTE,
        candidate=ReminderCandidate(
            rule_code=RULE_REST_DAY_NOTE,
            title="今天是恢复日",
            body="今天不练力量，散步、拉伸和补水也算训练的一部分。",
            target_path="/",
            params={"reminder_hour": ctx.reminder_hour},
        ),
    )


def _recall_inactive(ctx: ReminderContext, prefs: ReminderPreferences) -> RuleOutcome:
    if not prefs.recall_inactive_enabled:
        return RuleOutcome(RULE_RECALL_INACTIVE, skip_reason=SKIP_DISABLED)
    if ctx.last_checkin_date is None:
        return RuleOutcome(RULE_RECALL_INACTIVE)
    state = window_state(ctx.now_local, ctx.reminder_hour)
    if state == "before":
        return RuleOutcome(RULE_RECALL_INACTIVE)
    if state == "after":
        return RuleOutcome(RULE_RECALL_INACTIVE, skip_reason=SKIP_OUTSIDE_WINDOW)

    days = (ctx.now_local.date() - ctx.last_checkin_date).days
    due = days in (RECALL_FIRST_DAYS, RECALL_SECOND_DAYS) or (
        days >= RECALL_SLOWDOWN_DAYS and days % RECALL_SLOW_INTERVAL_DAYS == 0
    )
    if not due:
        return RuleOutcome(RULE_RECALL_INACTIVE)
    if ctx.reminders_sent_today > 0:
        # 同一天已经提醒过一次就不再叠加第二条催促；阶梯本身按 3/7/14 天触发。
        return RuleOutcome(RULE_RECALL_INACTIVE, skip_reason=SKIP_ALREADY_REMINDED_TODAY)

    return RuleOutcome(
        RULE_RECALL_INACTIVE,
        candidate=ReminderCandidate(
            rule_code=RULE_RECALL_INACTIVE,
            title=f"已经 {days} 天没练了",
            body="从一次 20 分钟的训练重新开始，比等一个完美的周一更有效。",
            target_path="/plan",
            params={"days_since_last_checkin": days},
        ),
    )


def _weekly_goal(ctx: ReminderContext, prefs: ReminderPreferences) -> RuleOutcome:
    """Weekly hit/gap share the trigger window; only one of them can apply per day."""
    reached = ctx.week_checkins >= prefs.weekly_goal_target
    week_end = ctx.weekday == 7
    gap_due = not reached and week_end
    if not reached and not gap_due:
        return RuleOutcome(RULE_WEEKLY_GOAL_HIT)
    rule_code = RULE_WEEKLY_GOAL_HIT if reached else RULE_WEEKLY_GOAL_GAP

    if not prefs.weekly_goal_enabled:
        return RuleOutcome(rule_code, skip_reason=SKIP_DISABLED)
    state = window_state(ctx.now_local, ctx.reminder_hour)
    if state == "before":
        return RuleOutcome(rule_code)
    if state == "after":
        return RuleOutcome(rule_code, skip_reason=SKIP_OUTSIDE_WINDOW)

    if reached:
        if RULE_WEEKLY_GOAL_HIT in ctx.rules_sent_this_week:
            return RuleOutcome(RULE_WEEKLY_GOAL_HIT, skip_reason=SKIP_ALREADY_THIS_WEEK)
        return RuleOutcome(
            RULE_WEEKLY_GOAL_HIT,
            candidate=ReminderCandidate(
                rule_code=RULE_WEEKLY_GOAL_HIT,
                title="本周目标达成",
                body=(
                    f"本周已经练了 {ctx.week_checkins} 次，"
                    f"达成 {prefs.weekly_goal_target} 次目标。"
                ),
                target_path="/",
                params={"week_checkins": ctx.week_checkins},
            ),
        )

    gap = prefs.weekly_goal_target - ctx.week_checkins
    if RULE_WEEKLY_GOAL_GAP in ctx.rules_sent_this_week:
        return RuleOutcome(RULE_WEEKLY_GOAL_GAP, skip_reason=SKIP_ALREADY_THIS_WEEK)
    return RuleOutcome(
        RULE_WEEKLY_GOAL_GAP,
        candidate=ReminderCandidate(
            rule_code=RULE_WEEKLY_GOAL_GAP,
            title="本周还差一点",
            body=f"距离本周目标还差 {gap} 次训练，今天补一次也算数。",
            target_path="/plan",
            params={"gap": gap},
        ),
    )


def _onboarding_nudge(ctx: ReminderContext, prefs: ReminderPreferences) -> RuleOutcome:
    if not prefs.onboarding_nudge_enabled:
        return RuleOutcome(RULE_ONBOARDING_NUDGE, skip_reason=SKIP_DISABLED)
    if ctx.has_plan and ctx.has_body_analysis:
        return RuleOutcome(RULE_ONBOARDING_NUDGE)
    if ctx.registered_days_ago < 1:
        return RuleOutcome(RULE_ONBOARDING_NUDGE)
    if ctx.onboarding_nudges_sent >= 2:
        return RuleOutcome(RULE_ONBOARDING_NUDGE, skip_reason=SKIP_ONBOARDING_EXHAUSTED)
    state = window_state(ctx.now_local, ctx.reminder_hour)
    if state == "before":
        return RuleOutcome(RULE_ONBOARDING_NUDGE)
    if state == "after":
        return RuleOutcome(RULE_ONBOARDING_NUDGE, skip_reason=SKIP_OUTSIDE_WINDOW)

    if not ctx.has_body_analysis:
        title, body, target = (
            "先做一次体型分析",
            "拍一张自然站姿照，我们就能排出更贴合你的计划。",
            "/analysis",
        )
    else:
        title, body, target = (
            "把这一周排出来",
            "体型分析已经就绪，生成一份本周计划就可以开始训练。",
            "/plan",
        )
    return RuleOutcome(
        RULE_ONBOARDING_NUDGE,
        candidate=ReminderCandidate(
            rule_code=RULE_ONBOARDING_NUDGE,
            title=title,
            body=body,
            target_path=target,
            params={},
        ),
    )


def evaluate_rules(ctx: ReminderContext, prefs: ReminderPreferences) -> list[RuleOutcome]:
    """Evaluate all six rules; the returned order is evaluation order."""
    return [
        _recall_inactive(ctx, prefs),
        _daily_training(ctx, prefs),
        _rest_day_note(ctx, prefs),
        _weekly_goal(ctx, prefs),
        _onboarding_nudge(ctx, prefs),
    ]
