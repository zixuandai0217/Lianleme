"""统一的本地时间抽象。

提醒按用户本地日界生成，而打卡统计过去直接拿服务器日期比较；两处口径不一致时会出现
「提醒说今天没练，统计说今天练了」。所有「今天/本地日期」判断从这里走，禁止再直接
用 ``datetime.date.today()`` 冒充用户本地日期。
"""
import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def timezone(name: str | None = None) -> ZoneInfo:
    """Resolve the configured local timezone (first version: a single deployment timezone)."""
    return ZoneInfo(name or settings.REMINDER_TIMEZONE)


def local_now(name: str | None = None) -> datetime.datetime:
    """Current time in the user-facing local timezone."""
    return datetime.datetime.now(timezone(name))


def to_local(moment: datetime.datetime, name: str | None = None) -> datetime.datetime:
    """Convert an aware datetime into the local timezone (naive values are assumed UTC)."""
    tz = timezone(name)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(tz)


def local_date(moment: datetime.datetime | None = None, name: str | None = None) -> datetime.date:
    """The local calendar date for a moment (defaults to now)."""
    return to_local(moment, name).date() if moment else local_now(name).date()
