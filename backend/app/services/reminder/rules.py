"""提醒规则（工单 33 只包含第一条规则）。

规则是纯函数：输入「本地时刻 + 今日安排 + 今日是否打卡」，输出候选提醒。它不碰数据库、
不读系统时钟，因此可以脱离环境单测；后续工单 34 会在同一签名下补齐其余五条规则，
调度与投递链路不需要改。
"""
import datetime
from dataclasses import dataclass, field

RULE_DAILY_TRAINING = "daily_training"

DEFAULT_REMINDER_HOUR = 19


@dataclass(frozen=True)
class ReminderCandidate:
    """一条待投递的提醒（渲染参数在 ``params`` 里，正文已渲染）。"""

    rule_code: str
    title: str
    body: str
    target_path: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingDayContext:
    """规则判定所需的今日事实；由服务层查库后传入。"""

    is_training_day: bool
    has_checked_in_today: bool
    focus: str | None = None
    estimated_duration: int | None = None


def evaluate_daily_training(
    now_local: datetime.datetime,
    context: TrainingDayContext,
    *,
    reminder_hour: int = DEFAULT_REMINDER_HOUR,
) -> list[ReminderCandidate]:
    """训练日、已过提醒时刻、当天尚未打卡 → 一条每日训练提醒。

    已打卡不发；休息日不发（恢复日提醒属于工单 34）；还没到提醒时刻不发。
    """
    if not context.is_training_day or context.has_checked_in_today:
        return []
    if now_local.hour < reminder_hour:
        return []

    focus = context.focus or "今日训练"
    duration = context.estimated_duration or 0
    body = f"{focus}还没练，练完记得打卡。"
    if duration:
        body = f"{focus}约 {duration} 分钟，练完记得打卡。"

    return [
        ReminderCandidate(
            rule_code=RULE_DAILY_TRAINING,
            title="今天的训练还没打卡",
            body=body,
            target_path="/",
            params={
                "focus": context.focus,
                "estimated_duration": context.estimated_duration,
                "reminder_hour": reminder_hour,
            },
        )
    ]
