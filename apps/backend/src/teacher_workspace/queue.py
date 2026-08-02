from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teacher_workspace.models import AIJob, AIJobAttempt, AIJobStatus


def now_utc() -> datetime:
    return datetime.now(UTC)


async def claim_next_job(
    session_factory: async_sessionmaker[AsyncSession], worker_id: str, lease_seconds: int
) -> uuid.UUID | None:
    async with session_factory() as session, session.begin():
        now = now_utc()
        await session.execute(
            update(AIJob)
            .where(
                AIJob.status == AIJobStatus.RUNNING,
                AIJob.lease_expires_at.is_not(None),
                AIJob.lease_expires_at < now,
            )
            .values(
                status=AIJobStatus.QUEUED,
                leased_by=None,
                lease_expires_at=None,
                error_code="LEASE_EXPIRED",
                error_message="Previous worker lease expired",
            )
        )
        statement = (
            select(AIJob)
            .where(
                AIJob.status == AIJobStatus.QUEUED,
                AIJob.available_at <= now,
            )
            .order_by(AIJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = await session.scalar(statement)
        if job is None:
            return None
        job.status = AIJobStatus.RUNNING
        job.leased_by = worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.attempts_count += 1
        session.add(
            AIJobAttempt(job_id=job.id, attempt_number=job.attempts_count, status="RUNNING")
        )
        return job.id


async def heartbeat(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: uuid.UUID,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    async with session_factory() as session, session.begin():
        job = await session.get(AIJob, job_id, with_for_update=True)
        if job is None or job.status != AIJobStatus.RUNNING or job.leased_by != worker_id:
            return False
        job.lease_expires_at = now_utc() + timedelta(seconds=lease_seconds)
        return True


async def complete_job(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: uuid.UUID,
    output: dict[str, object],
) -> None:
    async with session_factory() as session, session.begin():
        job = await session.get(AIJob, job_id, with_for_update=True)
        if job is None:
            raise LookupError(f"Unknown job {job_id}")
        job.status = AIJobStatus.SUCCEEDED
        job.output_payload = output
        job.leased_by = None
        job.lease_expires_at = None
        attempt = await session.scalar(
            select(AIJobAttempt).where(
                AIJobAttempt.job_id == job_id,
                AIJobAttempt.attempt_number == job.attempts_count,
            )
        )
        if attempt:
            attempt.status = "SUCCEEDED"
            attempt.finished_at = now_utc()


async def fail_job(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: uuid.UUID,
    error_code: str,
    safe_message: str,
) -> None:
    async with session_factory() as session, session.begin():
        job = await session.get(AIJob, job_id, with_for_update=True)
        if job is None:
            raise LookupError(f"Unknown job {job_id}")
        terminal = job.attempts_count >= job.max_attempts
        job.status = AIJobStatus.FAILED if terminal else AIJobStatus.QUEUED
        job.available_at = now_utc() + timedelta(seconds=2 ** job.attempts_count)
        job.error_code = error_code
        job.error_message = safe_message[:1000]
        job.leased_by = None
        job.lease_expires_at = None
        attempt = await session.scalar(
            select(AIJobAttempt).where(
                AIJobAttempt.job_id == job_id,
                AIJobAttempt.attempt_number == job.attempts_count,
            )
        )
        if attempt:
            attempt.status = "FAILED"
            attempt.error_code = error_code
            attempt.error_message = safe_message[:1000]
            attempt.finished_at = now_utc()
