from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.auth import CsrfUserDep, UserDep
from teacher_workspace.config import get_settings
from teacher_workspace.db import get_session
from teacher_workspace.docx_generator import (
    LessonDocumentMetadata,
    build_lesson_plan_docx,
    safe_docx_filename,
)
from teacher_workspace.models import (
    AIJob,
    AIJobStatus,
    AuditLog,
    DocumentVersion,
    DocumentVersionSource,
    Lesson,
    LessonDocument,
    PromptTemplate,
    PromptTemplateVersion,
    ReviewStatus,
    Student,
    StudentSubject,
    Subject,
)
from teacher_workspace.phase2_schemas import (
    AIJobResponse,
    AISettingsResponse,
    DocumentVersionResponse,
    GenerateLessonPlanRequest,
    LessonDocumentResponse,
    LessonPlanContent,
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    PromptTemplateVersionResponse,
    RegenerateSectionRequest,
    ReviewActionRequest,
    SaveDocumentRequest,
)
from teacher_workspace.phase2_service import (
    ensure_default_lesson_plan_template,
    resolve_template_version,
)
from teacher_workspace.prompts import lesson_plan_json_schema
from teacher_workspace.providers.ai import configured_ai_model, real_provider_configured
from teacher_workspace.providers.storage import LocalStorageProvider

router = APIRouter(prefix="/api/v1", tags=["lesson-documents"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise api_error(409, "VERSION_CONFLICT", "记录已被其他操作更新，请刷新后重试")


async def _owned_lesson(session: SessionDep, lesson_id: uuid.UUID, user_id: uuid.UUID) -> Lesson:
    lesson = await session.scalar(
        select(Lesson)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(Lesson.id == lesson_id, Student.owner_user_id == user_id)
    )
    if lesson is None:
        raise api_error(404, "LESSON_NOT_FOUND", "课程不存在")
    return lesson


async def _owned_document(
    session: SessionDep, document_id: uuid.UUID, user_id: uuid.UUID
) -> LessonDocument:
    document = await session.scalar(
        select(LessonDocument)
        .join(Lesson, Lesson.id == LessonDocument.lesson_id)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(LessonDocument.id == document_id, Student.owner_user_id == user_id)
    )
    if document is None:
        raise api_error(404, "DOCUMENT_NOT_FOUND", "教案不存在")
    return document


async def _document_response(
    session: SessionDep, document: LessonDocument
) -> LessonDocumentResponse:
    version = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == document.current_version_number,
        )
    )
    if version is None:
        raise api_error(409, "DOCUMENT_GENERATING", "教案尚未生成完成")
    return LessonDocumentResponse(
        id=document.id,
        lesson_id=document.lesson_id,
        title=document.title,
        status=document.status,
        current_version_number=document.current_version_number,
        approved_version_number=document.approved_version_number,
        version=document.version,
        current_version=DocumentVersionResponse.model_validate(version),
    )


def _template_response(
    template: PromptTemplate, version: PromptTemplateVersion
) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=template.id,
        template_key=template.template_key,
        name=template.name,
        purpose=template.purpose,
        grade_band=template.grade_band,
        subject_id=template.subject_id,
        current_version_number=template.current_version_number,
        current_version=PromptTemplateVersionResponse.model_validate(version),
    )


@router.get("/ai-settings", response_model=AISettingsResponse)
async def get_ai_settings(_: UserDep) -> AISettingsResponse:
    settings = get_settings()
    return AISettingsResponse(
        provider=settings.ai_provider,
        model=configured_ai_model(settings),
        real_provider_configured=real_provider_configured(settings),
    )


@router.get("/prompt-templates", response_model=list[PromptTemplateResponse])
async def list_prompt_templates(user: UserDep, session: SessionDep) -> list[PromptTemplateResponse]:
    await ensure_default_lesson_plan_template(session, user.id)
    await session.commit()
    rows = (
        await session.execute(
            select(PromptTemplate, PromptTemplateVersion)
            .join(
                PromptTemplateVersion,
                (PromptTemplateVersion.template_id == PromptTemplate.id)
                & (
                    PromptTemplateVersion.version_number
                    == PromptTemplate.current_version_number
                ),
            )
            .where(
                PromptTemplate.owner_user_id == user.id,
                PromptTemplate.archived_at.is_(None),
            )
            .order_by(PromptTemplate.grade_band.nullsfirst(), PromptTemplate.name)
        )
    ).all()
    return [_template_response(template, version) for template, version in rows]


@router.post(
    "/prompt-templates", response_model=PromptTemplateResponse, status_code=status.HTTP_201_CREATED
)
async def create_prompt_template(
    payload: PromptTemplateCreate,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> PromptTemplateResponse:
    if payload.subject_id is not None:
        subject = await session.scalar(
            select(Subject).where(
                Subject.id == payload.subject_id,
                Subject.owner_user_id == user.id,
                Subject.archived_at.is_(None),
            )
        )
        if subject is None:
            raise api_error(404, "SUBJECT_NOT_FOUND", "学科不存在")
    template = PromptTemplate(
        owner_user_id=user.id,
        subject_id=payload.subject_id,
        template_key=payload.template_key,
        name=payload.name,
        purpose=payload.purpose,
        grade_band=payload.grade_band,
        current_version_number=1,
    )
    session.add(template)
    await session.flush()
    version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        system_prompt=payload.system_prompt,
        user_prompt_template=payload.user_prompt_template,
        output_schema=lesson_plan_json_schema(),
        change_reason=payload.change_reason,
        created_by_user_id=user.id,
    )
    session.add(version)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="PROMPT_TEMPLATE_CREATED",
            entity_type="PromptTemplate",
            entity_id=str(template.id),
            change_summary={"template_key": template.template_key},
        )
    )
    await session.commit()
    return _template_response(template, version)


@router.put("/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
async def update_prompt_template(
    template_id: uuid.UUID,
    payload: PromptTemplateUpdate,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> PromptTemplateResponse:
    template = await session.scalar(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.owner_user_id == user.id,
            PromptTemplate.archived_at.is_(None),
        )
    )
    if template is None:
        raise api_error(404, "TEMPLATE_NOT_FOUND", "提示词模板不存在")
    check_version(template.current_version_number, payload.current_version_number)
    next_number = template.current_version_number + 1
    template.name = payload.name
    template.current_version_number = next_number
    version = PromptTemplateVersion(
        template_id=template.id,
        version_number=next_number,
        system_prompt=payload.system_prompt,
        user_prompt_template=payload.user_prompt_template,
        output_schema=lesson_plan_json_schema(),
        change_reason=payload.change_reason,
        created_by_user_id=user.id,
    )
    session.add(version)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="PROMPT_TEMPLATE_VERSION_CREATED",
            entity_type="PromptTemplate",
            entity_id=str(template.id),
            change_summary={"version_number": next_number},
        )
    )
    await session.commit()
    return _template_response(template, version)


@router.post(
    "/lessons/{lesson_id}/documents/generate",
    response_model=AIJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_lesson_document(
    lesson_id: uuid.UUID,
    payload: GenerateLessonPlanRequest,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> AIJobResponse:
    lesson = await _owned_lesson(session, lesson_id, user.id)
    template_version = await resolve_template_version(
        session, user.id, payload.template_id
    )
    document = await session.scalar(
        select(LessonDocument).where(
            LessonDocument.lesson_id == lesson.id,
            LessonDocument.document_type == "LESSON_PLAN",
        )
    )
    if document is None:
        document = LessonDocument(
            lesson_id=lesson.id,
            document_type="LESSON_PLAN",
            title=f"{lesson.theme} - 教师版教案",
            status=ReviewStatus.DRAFT,
            current_version_number=0,
            created_by_user_id=user.id,
        )
        session.add(document)
        await session.flush()
    running_jobs = (
        await session.scalars(
        select(AIJob).where(
            AIJob.owner_user_id == user.id,
            AIJob.task_type.in_(("lesson_plan.generate", "lesson_plan.regenerate_section")),
            AIJob.status.in_((AIJobStatus.QUEUED, AIJobStatus.RUNNING)),
        )
        )
    ).all()
    if any(job.input_payload.get("document_id") == str(document.id) for job in running_jobs):
        raise api_error(409, "GENERATION_IN_PROGRESS", "该教案已有生成任务正在处理")
    job = AIJob(
        owner_user_id=user.id,
        prompt_template_version_id=template_version.id,
        task_type="lesson_plan.generate",
        provider=get_settings().ai_provider,
        model=configured_ai_model(get_settings()),
        idempotency_key=f"lesson-plan:{document.id}:{document.version + 1}",
        input_payload={
            "document_id": str(document.id),
            "extra_requirements": payload.extra_requirements,
        },
        max_attempts=get_settings().job_max_attempts,
    )
    document.status = ReviewStatus.DRAFT
    document.version += 1
    session.add(job)
    await session.commit()
    return AIJobResponse.model_validate(job, from_attributes=True)


@router.get("/ai-jobs/{job_id}", response_model=AIJobResponse)
async def get_ai_job(job_id: uuid.UUID, user: UserDep, session: SessionDep) -> AIJobResponse:
    job = await session.scalar(
        select(AIJob).where(AIJob.id == job_id, AIJob.owner_user_id == user.id)
    )
    if job is None:
        raise api_error(404, "AI_JOB_NOT_FOUND", "生成任务不存在")
    return AIJobResponse.model_validate(job, from_attributes=True)


@router.get(
    "/lessons/{lesson_id}/document", response_model=LessonDocumentResponse
)
async def get_lesson_document(
    lesson_id: uuid.UUID, user: UserDep, session: SessionDep
) -> LessonDocumentResponse:
    await _owned_lesson(session, lesson_id, user.id)
    document = await session.scalar(
        select(LessonDocument).where(
            LessonDocument.lesson_id == lesson_id,
            LessonDocument.document_type == "LESSON_PLAN",
        )
    )
    if document is None:
        raise api_error(404, "DOCUMENT_NOT_FOUND", "该课程尚未生成教案")
    return await _document_response(session, document)


@router.get(
    "/lesson-documents/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
)
async def list_document_versions(
    document_id: uuid.UUID, user: UserDep, session: SessionDep
) -> list[DocumentVersionResponse]:
    await _owned_document(session, document_id, user.id)
    versions = (
        await session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        )
    ).all()
    return [DocumentVersionResponse.model_validate(row) for row in versions]


@router.put(
    "/lesson-documents/{document_id}", response_model=LessonDocumentResponse
)
async def save_lesson_document(
    document_id: uuid.UUID,
    payload: SaveDocumentRequest,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> LessonDocumentResponse:
    document = await _owned_document(session, document_id, user.id)
    check_version(document.version, payload.version)
    next_number = int(
        await session.scalar(
            select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                DocumentVersion.document_id == document.id
            )
        )
        or 0
    ) + 1
    version = DocumentVersion(
        document_id=document.id,
        version_number=next_number,
        source=DocumentVersionSource.MANUAL_EDIT,
        content=payload.content.model_dump(mode="json"),
        change_summary=payload.change_summary,
        created_by_user_id=user.id,
    )
    session.add(version)
    document.current_version_number = next_number
    document.status = ReviewStatus.DRAFT
    document.version += 1
    await session.commit()
    return await _document_response(session, document)


@router.post(
    "/lesson-documents/{document_id}/regenerate-section",
    response_model=AIJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_document_section(
    document_id: uuid.UUID,
    payload: RegenerateSectionRequest,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> AIJobResponse:
    document = await _owned_document(session, document_id, user.id)
    check_version(document.version, payload.version)
    running_jobs = (
        await session.scalars(
            select(AIJob).where(
                AIJob.owner_user_id == user.id,
                AIJob.task_type.in_(
                    ("lesson_plan.generate", "lesson_plan.regenerate_section")
                ),
                AIJob.status.in_((AIJobStatus.QUEUED, AIJobStatus.RUNNING)),
            )
        )
    ).all()
    if any(job.input_payload.get("document_id") == str(document.id) for job in running_jobs):
        raise api_error(409, "GENERATION_IN_PROGRESS", "该教案已有生成任务正在处理")
    template_version = await resolve_template_version(session, user.id, None)
    job = AIJob(
        owner_user_id=user.id,
        prompt_template_version_id=template_version.id,
        task_type="lesson_plan.regenerate_section",
        provider=get_settings().ai_provider,
        model=configured_ai_model(get_settings()),
        idempotency_key=(
            f"lesson-plan-section:{document.id}:{document.current_version_number}:"
            f"{payload.section}:{document.version + 1}"
        ),
        input_payload={
            "document_id": str(document.id),
            "section": payload.section,
            "instructions": payload.instructions,
        },
        max_attempts=get_settings().job_max_attempts,
    )
    session.add(job)
    document.status = ReviewStatus.DRAFT
    document.version += 1
    await session.commit()
    return AIJobResponse.model_validate(job, from_attributes=True)


async def _review_transition(
    session: SessionDep,
    document: LessonDocument,
    user_id: uuid.UUID,
    payload: ReviewActionRequest,
    target: ReviewStatus,
) -> LessonDocumentResponse:
    check_version(document.version, payload.version)
    current_version = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == document.current_version_number,
        )
    )
    if current_version is None:
        raise api_error(409, "DOCUMENT_VERSION_MISSING", "当前教案版本不存在")
    if target == ReviewStatus.PENDING_REVIEW and document.status not in {
        ReviewStatus.DRAFT,
        ReviewStatus.REJECTED,
    }:
        raise api_error(409, "INVALID_REVIEW_STATE", "当前状态不能提交审核")
    if (
        target in {ReviewStatus.APPROVED, ReviewStatus.REJECTED}
        and document.status != ReviewStatus.PENDING_REVIEW
    ):
        raise api_error(409, "INVALID_REVIEW_STATE", "只有待审核教案可以执行该操作")
    document.status = target
    current_version.status = target
    document.version += 1
    if target == ReviewStatus.APPROVED:
        if (
            document.approved_version_number is not None
            and document.approved_version_number != document.current_version_number
        ):
            previous_approved = await session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version_number == document.approved_version_number,
                )
            )
            if previous_approved is not None:
                previous_approved.status = ReviewStatus.SUPERSEDED
        document.approved_version_number = document.current_version_number
    session.add(
        AuditLog(
            actor_user_id=user_id,
            action=f"LESSON_DOCUMENT_{target.value}",
            entity_type="LessonDocument",
            entity_id=str(document.id),
            change_summary={
                "reason": payload.reason,
                "version_number": document.current_version_number,
            },
        )
    )
    await session.commit()
    return await _document_response(session, document)


@router.post(
    "/lesson-documents/{document_id}/submit", response_model=LessonDocumentResponse
)
async def submit_document(
    document_id: uuid.UUID,
    payload: ReviewActionRequest,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> LessonDocumentResponse:
    document = await _owned_document(session, document_id, user.id)
    return await _review_transition(
        session, document, user.id, payload, ReviewStatus.PENDING_REVIEW
    )


@router.post(
    "/lesson-documents/{document_id}/approve", response_model=LessonDocumentResponse
)
async def approve_document(
    document_id: uuid.UUID,
    payload: ReviewActionRequest,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> LessonDocumentResponse:
    document = await _owned_document(session, document_id, user.id)
    return await _review_transition(
        session, document, user.id, payload, ReviewStatus.APPROVED
    )


@router.post(
    "/lesson-documents/{document_id}/reject", response_model=LessonDocumentResponse
)
async def reject_document(
    document_id: uuid.UUID,
    payload: ReviewActionRequest,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> LessonDocumentResponse:
    document = await _owned_document(session, document_id, user.id)
    return await _review_transition(
        session, document, user.id, payload, ReviewStatus.REJECTED
    )


@router.post("/lesson-documents/{document_id}/export.docx")
async def export_document_docx(
    document_id: uuid.UUID,
    _: CsrfUserDep,
    user: UserDep,
    session: SessionDep,
) -> Response:
    document = await _owned_document(session, document_id, user.id)
    if document.approved_version_number is None:
        raise api_error(409, "DOCUMENT_NOT_APPROVED", "教案审核通过后才能导出")
    version = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == document.approved_version_number,
        )
    )
    row = (
        await session.execute(
            select(Lesson, Student, Subject)
            .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
            .join(Student, Student.id == StudentSubject.student_id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(Lesson.id == document.lesson_id, Student.owner_user_id == user.id)
        )
    ).first()
    if version is None or version.status != ReviewStatus.APPROVED or row is None:
        raise api_error(404, "DOCUMENT_VERSION_NOT_FOUND", "批准的教案版本不存在")
    lesson, student, subject = row
    metadata = LessonDocumentMetadata(
        student_alias=student.display_name,
        grade=student.grade or "未填写年级",
        subject=subject.name,
        theme=lesson.theme,
        scheduled_start=lesson.scheduled_start,
        planned_minutes=lesson.planned_minutes,
    )
    content = LessonPlanContent.model_validate(version.content)
    docx_bytes = build_lesson_plan_docx(metadata, content)
    object_key = f"documents/{user.id}/{document.id}/{version.version_number}.docx"
    storage = LocalStorageProvider(get_settings().local_storage_root)
    await storage.save(object_key, docx_bytes)
    version.docx_object_key = object_key
    await session.commit()
    filename = safe_docx_filename(metadata)
    return Response(
        content=docx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
