"""提醒偏好的读取与写入（工单 34）。

没有记录时返回缺省值而不落库：绝大多数用户从不改偏好，读路径不该产生写放大；
首次保存时才创建这一行（一对一，user_id 即主键）。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reminder_preference import DEFAULT_TIMEZONE, ReminderPreference
from app.services.reminder.rules import ReminderPreferences


def to_rules_preferences(record: ReminderPreference) -> ReminderPreferences:
    """Project the ORM row onto the pure-function input type."""
    return ReminderPreferences(
        daily_training_enabled=record.daily_training_enabled,
        rest_day_note_enabled=record.rest_day_note_enabled,
        recall_inactive_enabled=record.recall_inactive_enabled,
        weekly_goal_enabled=record.weekly_goal_enabled,
        onboarding_nudge_enabled=record.onboarding_nudge_enabled,
        quiet_hours_start=record.quiet_hours_start,
        quiet_hours_end=record.quiet_hours_end,
        daily_cap=record.daily_cap,
        weekly_goal_target=record.weekly_goal_target,
    )


async def get_row(db: AsyncSession, user_id: int) -> ReminderPreference | None:
    result = await db.execute(
        select(ReminderPreference).where(ReminderPreference.user_id == user_id)
    )
    return result.scalar_one_or_none()


def _default_row(user_id: int) -> ReminderPreference:
    """Transient row carrying the documented defaults (never persisted by a read)."""
    defaults = ReminderPreferences()
    return ReminderPreference(
        user_id=user_id,
        daily_training_enabled=defaults.daily_training_enabled,
        rest_day_note_enabled=defaults.rest_day_note_enabled,
        recall_inactive_enabled=defaults.recall_inactive_enabled,
        weekly_goal_enabled=defaults.weekly_goal_enabled,
        onboarding_nudge_enabled=defaults.onboarding_nudge_enabled,
        quiet_hours_start=defaults.quiet_hours_start,
        quiet_hours_end=defaults.quiet_hours_end,
        daily_cap=defaults.daily_cap,
        weekly_goal_target=defaults.weekly_goal_target,
        timezone=DEFAULT_TIMEZONE,
    )


async def get_effective(db: AsyncSession, user_id: int) -> ReminderPreference:
    """Saved preferences, or a transient default row (never persisted by a read)."""
    row = await get_row(db, user_id)
    return row if row is not None else _default_row(user_id)


async def upsert(
    db: AsyncSession, user_id: int, values: dict[str, object]
) -> ReminderPreference:
    """Create or fully update the user's preferences; returns the saved row."""
    row = await get_row(db, user_id)
    if row is None:
        row = ReminderPreference(user_id=user_id, **values)
        db.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
    await db.flush()
    await db.refresh(row)
    return row
