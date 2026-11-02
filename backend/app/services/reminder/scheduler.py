"""提醒调度宿主：进程内常驻 asyncio 长任务（工单 33）。

设计取舍：单实例部署 + 不引入 broker，因此用一个按固定间隔 tick 的长任务即可；
对业务只暴露 ``run_once()``，将来换成外部 cron / APScheduler 时不需要改规则与投递逻辑。
"""
import asyncio
import datetime
import logging
from collections.abc import Callable

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.local_time import local_now
from app.core.logging import (
    EVENT_REMINDER_TICK_FAILED,
    FIELD_ERROR_CLASS,
    log_event,
)
from app.services.reminder.reminder_service import ReminderService

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Owns the periodic tick loop; safe to start/stop more than once."""

    def __init__(
        self,
        session_factory: Callable = AsyncSessionLocal,
        interval_seconds: float | None = None,
        reminder_hour: int | None = None,
        now: Callable[[], datetime.datetime] | None = None,
    ):
        self._session_factory = session_factory
        self.interval_seconds = (
            settings.REMINDER_TICK_SECONDS if interval_seconds is None else interval_seconds
        )
        self._reminder_hour = reminder_hour
        self._now = now or local_now
        self._task: asyncio.Task | None = None
        self._tick_in_progress = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the loop once; repeated calls are no-ops (no double running)."""
        if self.is_running:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the loop and wait for it to settle; idempotent."""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _loop(self) -> None:
        # 先睡再 tick：启动瞬间不写业务数据，滚动发布时也不会和旧实例抢同一条记录。
        while True:
            await asyncio.sleep(self.interval_seconds)
            await self.run_once()

    async def run_once(self) -> dict:
        """Run one tick; never raises (a failing tick must not kill the loop)."""
        if self._tick_in_progress:
            return {"status": "skipped_reentrant"}

        self._tick_in_progress = True
        try:
            async with self._session_factory() as session:
                service = ReminderService(session, reminder_hour=self._reminder_hour)
                summary = await service.tick(self._now())
                await session.commit()
            return {
                "status": summary.status,
                "evaluated_users": summary.evaluated_users,
                "delivered": summary.delivered,
                "duplicates": summary.duplicates,
                "failed": summary.failed,
            }
        except Exception as exc:
            log_event(
                logger,
                EVENT_REMINDER_TICK_FAILED,
                message="提醒 tick 抛错，已捕获并继续",
                level=logging.ERROR,
                exc_info=exc,
                **{FIELD_ERROR_CLASS: type(exc).__name__},
            )
            return {"status": "error", "error_class": type(exc).__name__}
        finally:
            self._tick_in_progress = False
