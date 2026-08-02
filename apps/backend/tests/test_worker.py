from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from teacher_workspace.config import Settings
from teacher_workspace.models import AIJob, AIJobStatus, Base
from teacher_workspace.queue import claim_next_job, heartbeat
from teacher_workspace.worker import run_once


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_completes_mock_job(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(session_secret="x" * 32, worker_id="test-worker")
    async with session_factory() as session, session.begin():
        job = AIJob(task_type="mock.success", available_at=datetime.now(UTC), max_attempts=2)
        session.add(job)
        await session.flush()
        job_id = job.id

    assert await run_once(session_factory, settings)
    async with session_factory() as session:
        completed = await session.get(AIJob, job_id)
        assert completed is not None
        assert completed.status == AIJobStatus.SUCCEEDED
        assert completed.output_payload == {"mock": True, "task_type": "mock.success"}


@pytest.mark.asyncio
async def test_worker_requeues_then_fails(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(session_secret="x" * 32, worker_id="test-worker")
    async with session_factory() as session, session.begin():
        job = AIJob(task_type="mock.fail", available_at=datetime.now(UTC), max_attempts=2)
        session.add(job)
        await session.flush()
        job_id = job.id

    assert await run_once(session_factory, settings)
    async with session_factory() as session, session.begin():
        retry = await session.get(AIJob, job_id)
        assert retry is not None
        assert retry.status == AIJobStatus.QUEUED
        retry.available_at = datetime.now(UTC)

    assert await run_once(session_factory, settings)
    async with session_factory() as session:
        failed = await session.get(AIJob, job_id)
        assert failed is not None
        assert failed.status == AIJobStatus.FAILED
        assert failed.attempts_count == 2
        assert failed.error_message == "Task execution failed"


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed_and_heartbeat_extends_it(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session, session.begin():
        job = AIJob(
            task_type="mock.success",
            status=AIJobStatus.RUNNING,
            available_at=datetime.now(UTC) - timedelta(minutes=2),
            lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
            leased_by="dead-worker",
        )
        session.add(job)
        await session.flush()
        job_id = job.id

    claimed = await claim_next_job(session_factory, "replacement-worker", 60)
    assert claimed == job_id
    assert await heartbeat(session_factory, job_id, "replacement-worker", 120)
    assert not await heartbeat(session_factory, job_id, "wrong-worker", 120)
