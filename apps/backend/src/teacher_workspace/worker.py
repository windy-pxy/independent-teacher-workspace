import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teacher_workspace.account_deletion import purge_due_accounts
from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import dispose_engine, get_session_factory
from teacher_workspace.models import AIJob, User
from teacher_workspace.phase2_service import execute_lesson_plan_job
from teacher_workspace.phase3_service import execute_feedback_job
from teacher_workspace.phase4_service import (
    execute_question_set_job,
    execute_wrong_question_recognition_job,
)
from teacher_workspace.queue import cancel_job, claim_next_job, complete_job, fail_job

logger = logging.getLogger(__name__)


async def execute_mock_job(job: AIJob) -> dict[str, object]:
    if job.task_type == "mock.fail":
        raise RuntimeError("Requested mock failure")
    return {"mock": True, "task_type": job.task_type}


async def execute_job(
    job: AIJob,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> dict[str, object]:
    if job.task_type in {"lesson_plan.generate", "lesson_plan.regenerate_section"}:
        return await execute_lesson_plan_job(job, session_factory, settings)
    if job.task_type == "lesson_feedback.organize":
        return await execute_feedback_job(job, session_factory, settings)
    if job.task_type == "wrong_question.recognize":
        return await execute_wrong_question_recognition_job(job, session_factory, settings)
    if job.task_type == "question_set.generate":
        return await execute_question_set_job(job, session_factory, settings)
    return await execute_mock_job(job)


async def run_once(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    executor: Callable[[AIJob], Awaitable[dict[str, object]]] | None = None,
) -> bool:
    job_id = await claim_next_job(session_factory, settings.worker_id, settings.job_lease_seconds)
    if job_id is None:
        return False
    async with session_factory() as session:
        job = await session.get(AIJob, job_id)
        if job is None:
            return False
        if job.owner_user_id is not None:
            owner = await session.get(User, job.owner_user_id)
            if (
                owner is None
                or not owner.is_active
                or not owner.ai_access_enabled
                or owner.deletion_scheduled_for is not None
            ):
                await cancel_job(
                    session_factory,
                    job_id,
                    "AI_ACCESS_REVOKED",
                    "AI access was revoked before this task started",
                )
                return True
        try:
            output = (
                await executor(job)
                if executor is not None
                else await execute_job(job, session_factory, settings)
            )
        except Exception:
            logger.exception("Job %s failed with a sanitized worker error", job_id)
            await fail_job(
                session_factory,
                job_id,
                "WORKER_EXECUTION_FAILED",
                "Task execution failed",
            )
        else:
            await complete_job(session_factory, job_id, output)
    return True


async def run_forever() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    session_factory = get_session_factory()
    last_purge_check = 0.0
    try:
        while True:
            if time.monotonic() - last_purge_check >= 3600:
                try:
                    await purge_due_accounts(session_factory, settings)
                except Exception:
                    logger.exception("Scheduled account purge check failed")
                last_purge_check = time.monotonic()
            handled = await run_once(session_factory, settings)
            if not handled:
                await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
