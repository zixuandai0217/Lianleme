"""Contract tests for DB-driven analysis task leasing and recovery."""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.analysis_task import AnalysisTask
from app.models.user import User
from app.services.analysis_task_executor import AnalysisTaskExecutor


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'executor.db').as_posix()}")
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def task_factory(session_factory):
    async with session_factory() as session:
        user = User(openid="executor-user")
        session.add(user)
        await session.flush()
        task = AnalysisTask(
            task_id="executor-task",
            user_id=user.id,
            status="pending",
            stage="queued",
            attempt=0,
            progress=0,
            input_image_base64="image",
            expires_at=(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
            ),
        )
        session.add(task)
        await session.commit()
    return task.task_id


@pytest.mark.asyncio
async def test_claim_is_single_winner_and_increments_attempt(session_factory, task_factory):
    first = AnalysisTaskExecutor(session_factory)
    second = AnalysisTaskExecutor(session_factory)

    claimed = await first.claim_task(task_factory)
    duplicate = await second.claim_task(task_factory)

    assert claimed is not None
    assert duplicate is None
    assert claimed.status == "processing"
    assert claimed.attempt == 1
    assert claimed.lease_owner
    assert claimed.lease_expires_at is not None


@pytest.mark.asyncio
async def test_reclaim_requeues_stale_processing_task(session_factory, task_factory):
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_factory)
        assert task is not None
        task.status = "processing"
        task.attempt = 1
        task.lease_expires_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        )
        await session.commit()

    count = await AnalysisTaskExecutor(session_factory, max_attempts=3).reclaim_stale()

    assert count == 1
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_factory)
        assert task is not None
        assert task.status == "pending"
        assert task.lease_owner is None


@pytest.mark.asyncio
async def test_reclaim_exhaustion_is_terminal_failure(session_factory, task_factory):
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_factory)
        assert task is not None
        task.status = "processing"
        task.attempt = 3
        task.lease_expires_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        )
        await session.commit()

    count = await AnalysisTaskExecutor(session_factory, max_attempts=3).reclaim_stale()

    assert count == 1
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_factory)
        assert task is not None
        assert task.status == "failed"
        assert task.error_code == "retry_exhausted"


@pytest.mark.asyncio
async def test_expiry_marks_pending_task_expired(session_factory, task_factory):
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_factory)
        assert task is not None
        task.expires_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        )
        await session.commit()

    count = await AnalysisTaskExecutor(session_factory).expire_pending()

    assert count == 1
    async with session_factory() as session:
        task = await session.get(AnalysisTask, task_factory)
        assert task is not None
        assert task.status == "expired"
        assert task.error_code == "task_expired"
