from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teacher_workspace.config import Settings
from teacher_workspace.models import (
    AIJob,
    AIJobStatus,
    AuditLog,
    DocumentVersion,
    KnowledgePoint,
    Lesson,
    LessonDocument,
    PromptTemplate,
    Student,
    StudentSubject,
    Subject,
    UploadedMaterial,
    User,
    UserSession,
)
from teacher_workspace.providers.storage import create_storage_provider

logger = logging.getLogger(__name__)


async def owned_object_keys(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    material_keys = await session.scalars(
        select(UploadedMaterial.object_key).where(UploadedMaterial.owner_user_id == user_id)
    )
    docx_keys = await session.scalars(
        select(DocumentVersion.docx_object_key)
        .join(LessonDocument, LessonDocument.id == DocumentVersion.document_id)
        .join(Lesson, Lesson.id == LessonDocument.lesson_id)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(Student.owner_user_id == user_id, DocumentVersion.docx_object_key.is_not(None))
    )
    return {key for key in [*material_keys, *docx_keys] if key}


async def purge_due_accounts(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    cutoff = now or datetime.now(UTC)
    async with session_factory() as session:
        due_ids = list(
            await session.scalars(
                select(User.id).where(
                    User.deletion_scheduled_for.is_not(None),
                    User.deletion_scheduled_for <= cutoff,
                )
            )
        )
    storage = create_storage_provider(settings)
    purged = 0
    for user_id in due_ids:
        async with session_factory() as session, session.begin():
            user = await session.get(User, user_id, with_for_update=True)
            if user is None or user.deletion_scheduled_for is None:
                continue
            user.is_active = False
            user.ai_access_enabled = False
            user.ai_monthly_job_limit = 0
            await session.execute(
                update(UserSession)
                .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=cutoff)
            )
            await session.execute(
                update(AIJob)
                .where(
                    AIJob.owner_user_id == user.id,
                    AIJob.status.in_([AIJobStatus.QUEUED, AIJobStatus.RUNNING]),
                )
                .values(
                    status=AIJobStatus.CANCELED,
                    leased_by=None,
                    lease_expires_at=None,
                    error_code="ACCOUNT_DELETED",
                    error_message="Account deletion canceled this task",
                )
            )
            keys = await owned_object_keys(session, user.id)
        try:
            async with session_factory() as session, session.begin():
                user = await session.get(User, user_id, with_for_update=True)
                if user is None or user.deletion_scheduled_for is None:
                    continue
                subject_ids = list(
                    await session.scalars(
                        select(Subject.id).where(Subject.owner_user_id == user.id)
                    )
                )
                student_ids = list(
                    await session.scalars(
                        select(Student.id).where(Student.owner_user_id == user.id)
                    )
                )
                student_subject_ids = list(
                    await session.scalars(
                        select(StudentSubject.id).where(
                            StudentSubject.student_id.in_(student_ids)
                        )
                    )
                )
                if student_subject_ids:
                    await session.execute(
                        delete(Lesson).where(Lesson.student_subject_id.in_(student_subject_ids))
                    )
                    await session.execute(
                        delete(StudentSubject).where(StudentSubject.id.in_(student_subject_ids))
                    )
                if subject_ids:
                    await session.execute(
                        delete(KnowledgePoint).where(KnowledgePoint.subject_id.in_(subject_ids))
                    )
                    await session.execute(delete(Subject).where(Subject.id.in_(subject_ids)))
                if student_ids:
                    await session.execute(delete(Student).where(Student.id.in_(student_ids)))
                await session.execute(
                    delete(PromptTemplate).where(PromptTemplate.owner_user_id == user.id)
                )
                session.add(
                    AuditLog(
                        actor_user_id=None,
                        action="ACCOUNT_PURGED",
                        entity_type="User",
                        entity_id=str(user.id),
                        change_summary={},
                    )
                )
                await session.delete(user)
                await session.flush()
                for key in keys:
                    await storage.delete(key)
            purged += 1
        except Exception:
            logger.exception("Account purge failed for user id %s", user_id)
    return purged
