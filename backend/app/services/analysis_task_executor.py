"""Database-driven executor primitives for durable analysis tasks.

The executor deliberately exposes small async operations so the host can run one
or many workers without coupling callers to an in-process task dictionary.
"""
from __future__ import annotations

import datetime
import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import (
    EVENT_TASK_CLAIMED,
    EVENT_TASK_EXPIRED,
    EVENT_TASK_RECLAIMED,
    log_event,
)
from app.models.analysis_task import AnalysisTask

logger = logging.getLogger(__name__)


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


class AnalysisTaskExecutor:
    """Claim, reclaim, and expire analysis tasks using conditional DB writes."""

    def __init__(
        self,
        session_factory,
        *,
        lease_seconds: int = 120,
        max_attempts: int = 3,
    ) -> None:
        self.session_factory = session_factory
        self.lease_seconds = max(1, lease_seconds)
        self.max_attempts = max(1, max_attempts)

    async def claim_task(
        self, task_id: str, session: AsyncSession | None = None
    ) -> AnalysisTask | None:
        """Atomically claim one specific pending task for direct delivery."""
        owns_session = session is None
        db = session or self.session_factory()
        try:
            now = utc_now()
            candidate = await db.get(AnalysisTask, task_id)
            if (
                candidate is None
                or candidate.status != "pending"
                or (as_utc(candidate.expires_at) or now) <= now
            ):
                return None
            owner = uuid.uuid4().hex
            changed = await db.execute(
                update(AnalysisTask)
                .where(
                    AnalysisTask.task_id == task_id,
                    AnalysisTask.status == "pending",
                )
                .values(
                    status="processing",
                    stage="vision",
                    attempt=(candidate.attempt or 0) + 1,
                    started_at=candidate.started_at or now,
                    heartbeat_at=now,
                    lease_owner=owner,
                    lease_expires_at=now + datetime.timedelta(seconds=self.lease_seconds),
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                await db.rollback()
                return None
            await db.commit()
            log_event(
                logger,
                EVENT_TASK_CLAIMED,
                message="分析任务已认领",
                task_id=task_id,
                user_id=candidate.user_id,
                attempt=(candidate.attempt or 0) + 1,
            )
            return await db.get(AnalysisTask, task_id)
        finally:
            if owns_session:
                await db.close()

    async def claim(self, session: AsyncSession | None = None) -> AnalysisTask | None:
        """Atomically claim the oldest eligible pending task.

        SQLite serializes the conditional update; Postgres can additionally use
        row locks without changing this externally visible contract.
        """
        owns_session = session is None
        db = session or self.session_factory()
        try:
            now = utc_now()
            result = await db.execute(
                select(AnalysisTask)
                .where(
                    AnalysisTask.status == "pending",
                    AnalysisTask.expires_at > now,
                )
                .order_by(AnalysisTask.created_at)
                .limit(1)
            )
            candidate = result.scalar_one_or_none()
            if candidate is None:
                return None
            owner = uuid.uuid4().hex
            lease_until = now + datetime.timedelta(seconds=self.lease_seconds)
            changed = await db.execute(
                update(AnalysisTask)
                .where(
                    AnalysisTask.task_id == candidate.task_id,
                    AnalysisTask.status == "pending",
                )
                .values(
                    status="processing",
                    stage="vision",
                    attempt=(candidate.attempt or 0) + 1,
                    started_at=candidate.started_at or now,
                    heartbeat_at=now,
                    lease_owner=owner,
                    lease_expires_at=lease_until,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                await db.rollback()
                return None
            await db.commit()
            return await db.get(AnalysisTask, candidate.task_id)
        finally:
            if owns_session:
                await db.close()

    async def reclaim_stale(self, session: AsyncSession | None = None) -> int:
        """Return expired leases to pending, or fail after max attempts."""
        owns_session = session is None
        db = session or self.session_factory()
        try:
            now = utc_now()
            result = await db.execute(
                select(AnalysisTask).where(
                    AnalysisTask.status == "processing",
                    AnalysisTask.lease_expires_at.is_not(None),
                    AnalysisTask.lease_expires_at <= now,
                )
            )
            tasks = list(result.scalars())
            for task in tasks:
                task.lease_owner = None
                task.lease_expires_at = None
                task.heartbeat_at = None
                if (task.attempt or 0) >= self.max_attempts:
                    task.status = "failed"
                    task.stage = "done"
                    task.error_code = "retry_exhausted"
                    task.error_message = "多次重试后仍未完成，请重新发起"
                    task.error_retryable = True
                    task.finished_at = now
                else:
                    task.status = "pending"
                    task.stage = "queued"
                    task.progress = 0
                task.updated_at = now
            await db.commit()
            for task in tasks:
                log_event(
                    logger,
                    EVENT_TASK_RECLAIMED,
                    message="分析任务租约已回收",
                    task_id=task.task_id,
                    user_id=task.user_id,
                    attempt=task.attempt,
                )
            return len(tasks)
        finally:
            if owns_session:
                await db.close()

    async def expire_pending(self, session: AsyncSession | None = None) -> int:
        """Mark overdue pending or processing tasks as expired."""
        owns_session = session is None
        db = session or self.session_factory()
        try:
            now = utc_now()
            result = await db.execute(
                update(AnalysisTask)
                .where(
                    AnalysisTask.status.in_(("pending", "processing")),
                    AnalysisTask.expires_at <= now,
                )
                .values(
                    status="expired",
                    stage="done",
                    error_code="task_expired",
                    error_message="分析任务已过期，请重新发起",
                    error_retryable=True,
                    finished_at=now,
                    updated_at=now,
                )
            )
            await db.commit()
            count = int(result.rowcount or 0)
            if count:
                log_event(
                    logger,
                    EVENT_TASK_EXPIRED,
                    message="分析任务已过期",
                    count=count,
                )
            return count
        finally:
            if owns_session:
                await db.close()
