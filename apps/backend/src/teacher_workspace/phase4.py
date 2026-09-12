from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.auth import AIUserDep, CsrfUserDep, UserDep, reserve_ai_usage
from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.models import (
    AIJob,
    AuditLog,
    GeneratedQuestion,
    GeneratedQuestionKnowledgePoint,
    GeneratedQuestionSet,
    GeneratedQuestionSetVersion,
    KnowledgePoint,
    MasteryLevel,
    QuestionSetVersionSource,
    ReviewStatus,
    Student,
    StudentSubject,
    Subject,
    UploadedMaterial,
    WrongQuestion,
    WrongQuestionKnowledgePoint,
    WrongQuestionReview,
    WrongQuestionVersion,
    WrongQuestionVersionSource,
)
from teacher_workspace.phase2_schemas import AIJobResponse
from teacher_workspace.phase4_contract import GeneratedQuestionSetContent, WrongQuestionContent
from teacher_workspace.phase4_schemas import (
    ArchiveWrongQuestion,
    GenerateQuestionSetRequest,
    QuestionSetJobResponse,
    QuestionSetResponse,
    QuestionSetSave,
    QuestionSetVersionResponse,
    RecognitionJobResponse,
    ReviewAction,
    WrongQuestionCreate,
    WrongQuestionResponse,
    WrongQuestionReviewCreate,
    WrongQuestionReviewResponse,
    WrongQuestionSave,
    WrongQuestionVersionResponse,
)
from teacher_workspace.phase4_service import (
    ensure_phase4_template,
    owned_subject_context,
    resolve_knowledge_points,
    validate_knowledge_refs,
)
from teacher_workspace.prompts import (
    TARGETED_PRACTICE_TEMPLATE_KEY,
    WRONG_QUESTION_RECOGNITION_TEMPLATE_KEY,
)
from teacher_workspace.providers.ai import configured_ai_model, configured_vision_model
from teacher_workspace.providers.storage import create_storage_provider
from teacher_workspace.storage_quota import ensure_upload_capacity

router = APIRouter(prefix="/api/v1", tags=["wrong-questions", "practice"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise api_error(409, "VERSION_CONFLICT", "记录已更新，请刷新后重试")


async def owned_wrong_question(
    session: AsyncSession,
    question_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> WrongQuestion:
    statement = (
        select(WrongQuestion)
        .join(StudentSubject, StudentSubject.id == WrongQuestion.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(WrongQuestion.id == question_id, Student.owner_user_id == user_id)
    )
    if for_update:
        statement = statement.with_for_update()
    question = await session.scalar(statement)
    if question is None:
        raise api_error(404, "WRONG_QUESTION_NOT_FOUND", "错题不存在")
    return question


async def owned_question_set(
    session: AsyncSession,
    set_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> GeneratedQuestionSet:
    statement = (
        select(GeneratedQuestionSet)
        .join(StudentSubject, StudentSubject.id == GeneratedQuestionSet.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(GeneratedQuestionSet.id == set_id, Student.owner_user_id == user_id)
    )
    if for_update:
        statement = statement.with_for_update()
    question_set = await session.scalar(statement)
    if question_set is None:
        raise api_error(404, "QUESTION_SET_NOT_FOUND", "练习题集不存在")
    return question_set


async def wrong_question_response(
    session: AsyncSession, question: WrongQuestion
) -> WrongQuestionResponse:
    row = (
        await session.execute(
            select(Student.display_name, Subject.name)
            .join(StudentSubject, StudentSubject.student_id == Student.id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(StudentSubject.id == question.student_subject_id)
        )
    ).one()
    version = await session.scalar(
        select(WrongQuestionVersion).where(
            WrongQuestionVersion.wrong_question_id == question.id,
            WrongQuestionVersion.version_number == question.current_version_number,
        )
    )
    if version is None:
        raise api_error(409, "WRONG_QUESTION_VERSION_MISSING", "当前错题版本不存在")
    return WrongQuestionResponse(
        id=question.id,
        student_subject_id=question.student_subject_id,
        student_name=row[0],
        subject_name=row[1],
        status=question.status,
        current_version_number=question.current_version_number,
        approved_version_number=question.approved_version_number,
        mastery_status=question.mastery_status,
        last_reviewed_at=question.last_reviewed_at,
        review_count=question.review_count,
        version=question.version,
        current_version=WrongQuestionVersionResponse.model_validate(version),
    )


async def question_set_response(
    session: AsyncSession, question_set: GeneratedQuestionSet
) -> QuestionSetResponse:
    row = (
        await session.execute(
            select(Student.display_name, Subject.name)
            .join(StudentSubject, StudentSubject.student_id == Student.id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(StudentSubject.id == question_set.student_subject_id)
        )
    ).one()
    current = None
    if question_set.current_version_number:
        version = await session.scalar(
            select(GeneratedQuestionSetVersion).where(
                GeneratedQuestionSetVersion.question_set_id == question_set.id,
                GeneratedQuestionSetVersion.version_number
                == question_set.current_version_number,
            )
        )
        if version is None:
            raise api_error(409, "QUESTION_SET_VERSION_MISSING", "当前练习版本不存在")
        current = QuestionSetVersionResponse.model_validate(version)
    return QuestionSetResponse(
        id=question_set.id,
        student_subject_id=question_set.student_subject_id,
        student_name=row[0],
        subject_name=row[1],
        title=question_set.title,
        status=question_set.status,
        current_version_number=question_set.current_version_number,
        approved_version_number=question_set.approved_version_number,
        parameters=question_set.parameters,
        version=question_set.version,
        current_version=current,
    )


async def replace_wrong_question_points(
    session: AsyncSession,
    question: WrongQuestion,
    content: WrongQuestionContent,
) -> None:
    student_subject = await session.get(StudentSubject, question.student_subject_id)
    if student_subject is None:
        raise api_error(409, "STUDENT_SUBJECT_MISSING", "学生学科档案不存在")
    points = await resolve_knowledge_points(
        session, student_subject.subject_id, content.knowledge_points
    )
    await session.execute(
        delete(WrongQuestionKnowledgePoint).where(
            WrongQuestionKnowledgePoint.wrong_question_id == question.id
        )
    )
    session.add_all(
        [
            WrongQuestionKnowledgePoint(
                wrong_question_id=question.id, knowledge_point_id=point.id
            )
            for point in points
        ]
    )


@router.get("/wrong-questions", response_model=list[WrongQuestionResponse])
async def list_wrong_questions(
    user: UserDep,
    session: SessionDep,
    student_subject_id: uuid.UUID | None = None,
) -> list[WrongQuestionResponse]:
    statement = (
        select(WrongQuestion)
        .join(StudentSubject, StudentSubject.id == WrongQuestion.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(Student.owner_user_id == user.id, WrongQuestion.archived_at.is_(None))
        .order_by(WrongQuestion.updated_at.desc())
    )
    if student_subject_id is not None:
        statement = statement.where(WrongQuestion.student_subject_id == student_subject_id)
    questions = (await session.scalars(statement)).all()
    return [await wrong_question_response(session, item) for item in questions]


@router.post(
    "/wrong-questions", response_model=WrongQuestionResponse, status_code=status.HTTP_201_CREATED
)
async def create_wrong_question(
    payload: WrongQuestionCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> WrongQuestionResponse:
    student_subject, _, subject = await owned_subject_context(
        session, payload.student_subject_id, user.id
    )
    try:
        payload.content.validate_for_approval()
    except ValueError as exc:
        raise api_error(422, "INCOMPLETE_WRONG_QUESTION", str(exc)) from exc
    await validate_knowledge_refs(session, subject.id, payload.content.knowledge_points)
    question = WrongQuestion(
        student_subject_id=student_subject.id,
        status=ReviewStatus.APPROVED,
        current_version_number=1,
        approved_version_number=1,
        mastery_status=payload.mastery_status,
        created_by_user_id=user.id,
    )
    session.add(question)
    await session.flush()
    version = WrongQuestionVersion(
        wrong_question_id=question.id,
        version_number=1,
        source=WrongQuestionVersionSource.MANUAL_ENTRY,
        status=ReviewStatus.APPROVED,
        content=payload.content.model_dump(mode="json"),
        change_summary="教师手工录入并确认",
        created_by_user_id=user.id,
    )
    session.add(version)
    await replace_wrong_question_points(session, question, payload.content)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="WRONG_QUESTION_CREATED",
            entity_type="WrongQuestion",
            entity_id=str(question.id),
            change_summary={"source": "MANUAL_ENTRY"},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()
    return await wrong_question_response(session, question)


def detect_image(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    return None


@router.post(
    "/wrong-questions/from-image",
    response_model=RecognitionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_wrong_question_from_image(
    request: Request,
    user: AIUserDep,
    session: SessionDep,
    settings: SettingsDep,
    student_subject_id: Annotated[uuid.UUID, Form()],
    image: Annotated[UploadFile, File()],
) -> RecognitionJobResponse:
    student_subject, _, _ = await owned_subject_context(session, student_subject_id, user.id)
    filename = PurePath(image.filename or "question-image").name
    extension = PurePath(filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        raise api_error(422, "INVALID_FILE_EXTENSION", "仅支持 PNG、JPG 或 JPEG 图片")
    content = await image.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise api_error(413, "FILE_TOO_LARGE", "图片超过允许的大小")
    detected = detect_image(content)
    if detected is None or image.content_type != detected[0]:
        raise api_error(422, "INVALID_FILE_CONTENT", "图片类型、MIME 或文件内容不一致")
    await ensure_upload_capacity(session, user.id, len(content), settings)
    await reserve_ai_usage(user, session)
    object_key = f"wrong-questions/{user.id}/{uuid.uuid4()}{detected[1]}"
    storage = create_storage_provider(settings)
    await storage.save(object_key, content)
    try:
        material = UploadedMaterial(
            owner_user_id=user.id,
            student_subject_id=student_subject.id,
            purpose="WRONG_QUESTION_IMAGE",
            display_name=filename[:255],
            object_key=object_key,
            mime_type=detected[0],
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            processing_status="QUEUED",
        )
        question = WrongQuestion(
            student_subject_id=student_subject.id,
            status=ReviewStatus.DRAFT,
            current_version_number=1,
            mastery_status=MasteryLevel.WEAK,
            created_by_user_id=user.id,
        )
        session.add_all([material, question])
        await session.flush()
        source_version = WrongQuestionVersion(
            wrong_question_id=question.id,
            version_number=1,
            source=WrongQuestionVersionSource.MANUAL_ENTRY,
            status=ReviewStatus.DRAFT,
            content=WrongQuestionContent(
                question_text="等待图片识别",
                recognition_notes="原图已安全保存，识别结果尚未生成。",
            ).model_dump(mode="json"),
            image_material_id=material.id,
            change_summary="上传图片，等待识别",
            created_by_user_id=user.id,
        )
        template = await ensure_phase4_template(
            session, user.id, WRONG_QUESTION_RECOGNITION_TEMPLATE_KEY
        )
        job = AIJob(
            owner_user_id=user.id,
            prompt_template_version_id=template.id,
            task_type="wrong_question.recognize",
            provider=settings.vision_ai_provider,
            model=configured_vision_model(settings),
            idempotency_key=f"wrong-question-recognition:{question.id}:1",
            input_payload={
                "wrong_question_id": str(question.id),
                "source_version_number": 1,
            },
            max_attempts=settings.job_max_attempts,
        )
        session.add_all([source_version, job])
        session.add(
            AuditLog(
                actor_user_id=user.id,
                action="WRONG_QUESTION_IMAGE_UPLOADED",
                entity_type="WrongQuestion",
                entity_id=str(question.id),
                change_summary={"mime_type": detected[0], "size_bytes": len(content)},
                request_id=getattr(request.state, "request_id", None),
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await storage.delete(object_key)
        raise
    return RecognitionJobResponse(
        wrong_question=await wrong_question_response(session, question),
        job=AIJobResponse.model_validate(job, from_attributes=True),
    )


@router.get("/uploaded-materials/{material_id}")
async def download_material(
    material_id: uuid.UUID, user: UserDep, session: SessionDep, settings: SettingsDep
) -> Response:
    material = await session.scalar(
        select(UploadedMaterial).where(
            UploadedMaterial.id == material_id,
            UploadedMaterial.owner_user_id == user.id,
            UploadedMaterial.archived_at.is_(None),
        )
    )
    if material is None:
        raise api_error(404, "MATERIAL_NOT_FOUND", "图片不存在")
    content = await create_storage_provider(settings).read(material.object_key)
    return Response(
        content=content,
        media_type=material.mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/wrong-questions/{question_id}", response_model=WrongQuestionResponse)
async def get_wrong_question(
    question_id: uuid.UUID, user: UserDep, session: SessionDep
) -> WrongQuestionResponse:
    return await wrong_question_response(
        session, await owned_wrong_question(session, question_id, user.id)
    )


@router.get(
    "/wrong-questions/{question_id}/versions",
    response_model=list[WrongQuestionVersionResponse],
)
async def list_wrong_question_versions(
    question_id: uuid.UUID, user: UserDep, session: SessionDep
) -> list[WrongQuestionVersionResponse]:
    await owned_wrong_question(session, question_id, user.id)
    versions = (
        await session.scalars(
            select(WrongQuestionVersion)
            .where(WrongQuestionVersion.wrong_question_id == question_id)
            .order_by(WrongQuestionVersion.version_number.desc())
        )
    ).all()
    return [WrongQuestionVersionResponse.model_validate(item) for item in versions]


@router.put("/wrong-questions/{question_id}", response_model=WrongQuestionResponse)
async def save_wrong_question(
    question_id: uuid.UUID,
    payload: WrongQuestionSave,
    user: CsrfUserDep,
    session: SessionDep,
) -> WrongQuestionResponse:
    question = await owned_wrong_question(session, question_id, user.id, for_update=True)
    check_version(question.version, payload.version)
    if question.status == ReviewStatus.APPROVED:
        raise api_error(409, "WRONG_QUESTION_APPROVED", "已批准错题不可直接修改")
    student_subject = await session.get(StudentSubject, question.student_subject_id)
    if student_subject is None:
        raise api_error(409, "STUDENT_SUBJECT_MISSING", "学生学科档案不存在")
    await validate_knowledge_refs(
        session, student_subject.subject_id, payload.content.knowledge_points
    )
    current = await session.scalar(
        select(WrongQuestionVersion).where(
            WrongQuestionVersion.wrong_question_id == question.id,
            WrongQuestionVersion.version_number == question.current_version_number,
        )
    )
    if current is not None:
        current.status = ReviewStatus.SUPERSEDED
    number = question.current_version_number + 1
    version = WrongQuestionVersion(
        wrong_question_id=question.id,
        version_number=number,
        source=WrongQuestionVersionSource.MANUAL_EDIT,
        status=ReviewStatus.DRAFT,
        content=payload.content.model_dump(mode="json"),
        image_material_id=current.image_material_id if current else None,
        change_summary=payload.change_summary,
        created_by_user_id=user.id,
    )
    session.add(version)
    question.current_version_number = number
    question.status = ReviewStatus.DRAFT
    question.version += 1
    await session.commit()
    return await wrong_question_response(session, question)


async def transition_wrong_question(
    session: AsyncSession,
    question: WrongQuestion,
    user_id: uuid.UUID,
    payload: ReviewAction,
    target: ReviewStatus,
) -> WrongQuestionResponse:
    check_version(question.version, payload.version)
    version = await session.scalar(
        select(WrongQuestionVersion).where(
            WrongQuestionVersion.wrong_question_id == question.id,
            WrongQuestionVersion.version_number == question.current_version_number,
        )
    )
    if version is None:
        raise api_error(409, "WRONG_QUESTION_VERSION_MISSING", "当前错题版本不存在")
    allowed = {
        ReviewStatus.PENDING_REVIEW: {ReviewStatus.DRAFT, ReviewStatus.REJECTED},
        ReviewStatus.APPROVED: {ReviewStatus.PENDING_REVIEW},
        ReviewStatus.REJECTED: {ReviewStatus.PENDING_REVIEW},
    }
    if question.status not in allowed[target]:
        raise api_error(409, "INVALID_REVIEW_TRANSITION", "当前状态不允许该审核操作")
    content = WrongQuestionContent.model_validate(version.content)
    if target == ReviewStatus.APPROVED:
        try:
            content.validate_for_approval()
        except ValueError as exc:
            raise api_error(422, "INCOMPLETE_WRONG_QUESTION", str(exc)) from exc
        await replace_wrong_question_points(session, question, content)
        question.approved_version_number = version.version_number
    question.status = target
    version.status = target
    question.version += 1
    session.add(
        AuditLog(
            actor_user_id=user_id,
            action=f"WRONG_QUESTION_{target.value}",
            entity_type="WrongQuestion",
            entity_id=str(question.id),
            change_summary={"reason": payload.reason, "version": version.version_number},
        )
    )
    await session.commit()
    return await wrong_question_response(session, question)


@router.post("/wrong-questions/{question_id}/submit", response_model=WrongQuestionResponse)
async def submit_wrong_question(
    question_id: uuid.UUID, payload: ReviewAction, user: CsrfUserDep, session: SessionDep
) -> WrongQuestionResponse:
    question = await owned_wrong_question(session, question_id, user.id, for_update=True)
    return await transition_wrong_question(
        session, question, user.id, payload, ReviewStatus.PENDING_REVIEW
    )


@router.post("/wrong-questions/{question_id}/approve", response_model=WrongQuestionResponse)
async def approve_wrong_question(
    question_id: uuid.UUID, payload: ReviewAction, user: CsrfUserDep, session: SessionDep
) -> WrongQuestionResponse:
    question = await owned_wrong_question(session, question_id, user.id, for_update=True)
    return await transition_wrong_question(
        session, question, user.id, payload, ReviewStatus.APPROVED
    )


@router.post("/wrong-questions/{question_id}/reject", response_model=WrongQuestionResponse)
async def reject_wrong_question(
    question_id: uuid.UUID, payload: ReviewAction, user: CsrfUserDep, session: SessionDep
) -> WrongQuestionResponse:
    question = await owned_wrong_question(session, question_id, user.id, for_update=True)
    return await transition_wrong_question(
        session, question, user.id, payload, ReviewStatus.REJECTED
    )


@router.post(
    "/wrong-questions/{question_id}/reviews",
    response_model=WrongQuestionReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_wrong_question_review(
    question_id: uuid.UUID,
    payload: WrongQuestionReviewCreate,
    user: CsrfUserDep,
    session: SessionDep,
) -> WrongQuestionReviewResponse:
    question = await owned_wrong_question(session, question_id, user.id, for_update=True)
    check_version(question.version, payload.version)
    if question.status != ReviewStatus.APPROVED:
        raise api_error(409, "WRONG_QUESTION_NOT_APPROVED", "仅正式错题可以记录复习")
    reviewed_at = payload.reviewed_at or datetime.now(UTC)
    review = WrongQuestionReview(
        wrong_question_id=question.id,
        result_level=payload.result_level,
        notes=payload.notes,
        reviewed_at=reviewed_at,
        created_by_user_id=user.id,
    )
    session.add(review)
    question.mastery_status = payload.result_level
    question.last_reviewed_at = reviewed_at
    question.review_count += 1
    question.version += 1
    await session.commit()
    return WrongQuestionReviewResponse.model_validate(review)


@router.get(
    "/wrong-questions/{question_id}/reviews",
    response_model=list[WrongQuestionReviewResponse],
)
async def list_wrong_question_reviews(
    question_id: uuid.UUID, user: UserDep, session: SessionDep
) -> list[WrongQuestionReviewResponse]:
    await owned_wrong_question(session, question_id, user.id)
    reviews = (
        await session.scalars(
            select(WrongQuestionReview)
            .where(WrongQuestionReview.wrong_question_id == question_id)
            .order_by(WrongQuestionReview.reviewed_at.desc())
        )
    ).all()
    return [WrongQuestionReviewResponse.model_validate(item) for item in reviews]


@router.post("/wrong-questions/{question_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_wrong_question(
    question_id: uuid.UUID,
    payload: ArchiveWrongQuestion,
    user: CsrfUserDep,
    session: SessionDep,
) -> Response:
    question = await owned_wrong_question(session, question_id, user.id, for_update=True)
    check_version(question.version, payload.version)
    question.archived_at = datetime.now(UTC)
    question.version += 1
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="WRONG_QUESTION_ARCHIVED",
            entity_type="WrongQuestion",
            entity_id=str(question.id),
            change_summary={"reason": payload.reason},
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/question-sets", response_model=list[QuestionSetResponse])
async def list_question_sets(
    user: UserDep, session: SessionDep
) -> list[QuestionSetResponse]:
    items = (
        await session.scalars(
            select(GeneratedQuestionSet)
            .join(StudentSubject, StudentSubject.id == GeneratedQuestionSet.student_subject_id)
            .join(Student, Student.id == StudentSubject.student_id)
            .where(
                Student.owner_user_id == user.id,
                GeneratedQuestionSet.archived_at.is_(None),
            )
            .order_by(GeneratedQuestionSet.updated_at.desc())
        )
    ).all()
    return [await question_set_response(session, item) for item in items]


@router.post(
    "/question-sets/generate",
    response_model=QuestionSetJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_question_set(
    payload: GenerateQuestionSetRequest,
    user: AIUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> QuestionSetJobResponse:
    student_subject, _, subject = await owned_subject_context(
        session, payload.student_subject_id, user.id
    )
    if payload.knowledge_point_ids:
        found = set(
            (
                await session.scalars(
                    select(KnowledgePoint.id).where(
                        KnowledgePoint.id.in_(payload.knowledge_point_ids),
                        KnowledgePoint.subject_id == subject.id,
                        KnowledgePoint.archived_at.is_(None),
                    )
                )
            ).all()
        )
        if found != set(payload.knowledge_point_ids):
            raise api_error(422, "INVALID_KNOWLEDGE_POINT", "包含不属于该学科的知识点")
    if payload.wrong_question_ids:
        count = int(
            await session.scalar(
                select(func.count(WrongQuestion.id))
                .join(StudentSubject, StudentSubject.id == WrongQuestion.student_subject_id)
                .where(
                    WrongQuestion.id.in_(payload.wrong_question_ids),
                    WrongQuestion.student_subject_id == student_subject.id,
                    WrongQuestion.status == ReviewStatus.APPROVED,
                    WrongQuestion.archived_at.is_(None),
                )
            )
            or 0
        )
        if count != len(set(payload.wrong_question_ids)):
            raise api_error(422, "INVALID_WRONG_QUESTION", "包含不可用或未批准的错题")
    await reserve_ai_usage(user, session)
    parameters = payload.model_dump(mode="json")
    question_set = GeneratedQuestionSet(
        student_subject_id=student_subject.id,
        title=payload.title,
        status=ReviewStatus.DRAFT,
        current_version_number=0,
        parameters=parameters,
        created_by_user_id=user.id,
    )
    session.add(question_set)
    await session.flush()
    template = await ensure_phase4_template(session, user.id, TARGETED_PRACTICE_TEMPLATE_KEY)
    job = AIJob(
        owner_user_id=user.id,
        prompt_template_version_id=template.id,
        task_type="question_set.generate",
        provider=settings.ai_provider,
        model=configured_ai_model(settings),
        idempotency_key=f"question-set:{question_set.id}:1",
        input_payload={"question_set_id": str(question_set.id)},
        max_attempts=settings.job_max_attempts,
    )
    session.add(job)
    await session.commit()
    return QuestionSetJobResponse(
        question_set=await question_set_response(session, question_set),
        job=AIJobResponse.model_validate(job, from_attributes=True),
    )


@router.get("/question-sets/{set_id}", response_model=QuestionSetResponse)
async def get_question_set(
    set_id: uuid.UUID, user: UserDep, session: SessionDep
) -> QuestionSetResponse:
    return await question_set_response(
        session, await owned_question_set(session, set_id, user.id)
    )


@router.get(
    "/question-sets/{set_id}/versions", response_model=list[QuestionSetVersionResponse]
)
async def list_question_set_versions(
    set_id: uuid.UUID, user: UserDep, session: SessionDep
) -> list[QuestionSetVersionResponse]:
    await owned_question_set(session, set_id, user.id)
    versions = (
        await session.scalars(
            select(GeneratedQuestionSetVersion)
            .where(GeneratedQuestionSetVersion.question_set_id == set_id)
            .order_by(GeneratedQuestionSetVersion.version_number.desc())
        )
    ).all()
    return [QuestionSetVersionResponse.model_validate(item) for item in versions]


@router.put("/question-sets/{set_id}", response_model=QuestionSetResponse)
async def save_question_set(
    set_id: uuid.UUID,
    payload: QuestionSetSave,
    user: CsrfUserDep,
    session: SessionDep,
) -> QuestionSetResponse:
    question_set = await owned_question_set(session, set_id, user.id, for_update=True)
    check_version(question_set.version, payload.version)
    if question_set.status == ReviewStatus.APPROVED:
        raise api_error(409, "QUESTION_SET_APPROVED", "已批准练习不可直接修改")
    student_subject = await session.get(StudentSubject, question_set.student_subject_id)
    if student_subject is None:
        raise api_error(409, "STUDENT_SUBJECT_MISSING", "学生学科档案不存在")
    for item in payload.content.questions:
        await validate_knowledge_refs(session, student_subject.subject_id, item.knowledge_points)
    current = await session.scalar(
        select(GeneratedQuestionSetVersion).where(
            GeneratedQuestionSetVersion.question_set_id == question_set.id,
            GeneratedQuestionSetVersion.version_number == question_set.current_version_number,
        )
    )
    if current is not None:
        current.status = ReviewStatus.SUPERSEDED
    number = question_set.current_version_number + 1
    session.add(
        GeneratedQuestionSetVersion(
            question_set_id=question_set.id,
            version_number=number,
            source=QuestionSetVersionSource.MANUAL_EDIT,
            status=ReviewStatus.DRAFT,
            content=payload.content.model_dump(mode="json"),
            change_summary=payload.change_summary,
            created_by_user_id=user.id,
        )
    )
    question_set.title = payload.content.title
    question_set.current_version_number = number
    question_set.status = ReviewStatus.DRAFT
    question_set.version += 1
    await session.commit()
    return await question_set_response(session, question_set)


async def transition_question_set(
    session: AsyncSession,
    question_set: GeneratedQuestionSet,
    user_id: uuid.UUID,
    payload: ReviewAction,
    target: ReviewStatus,
) -> QuestionSetResponse:
    check_version(question_set.version, payload.version)
    version = await session.scalar(
        select(GeneratedQuestionSetVersion).where(
            GeneratedQuestionSetVersion.question_set_id == question_set.id,
            GeneratedQuestionSetVersion.version_number == question_set.current_version_number,
        )
    )
    if version is None:
        raise api_error(409, "QUESTION_SET_VERSION_MISSING", "当前练习版本不存在")
    allowed = {
        ReviewStatus.PENDING_REVIEW: {ReviewStatus.DRAFT, ReviewStatus.REJECTED},
        ReviewStatus.APPROVED: {ReviewStatus.PENDING_REVIEW},
        ReviewStatus.REJECTED: {ReviewStatus.PENDING_REVIEW},
    }
    if question_set.status not in allowed[target]:
        raise api_error(409, "INVALID_REVIEW_TRANSITION", "当前状态不允许该审核操作")
    content = GeneratedQuestionSetContent.model_validate(version.content)
    if target == ReviewStatus.APPROVED:
        student_subject = await session.get(StudentSubject, question_set.student_subject_id)
        if student_subject is None:
            raise api_error(409, "STUDENT_SUBJECT_MISSING", "学生学科档案不存在")
        for item in content.questions:
            await validate_knowledge_refs(
                session, student_subject.subject_id, item.knowledge_points
            )
        question_set.approved_version_number = version.version_number
        await session.execute(
            delete(GeneratedQuestion).where(
                GeneratedQuestion.question_set_id == question_set.id
            )
        )
        for order, item in enumerate(content.questions, start=1):
            generated = GeneratedQuestion(
                question_set_id=question_set.id,
                approved_version_number=version.version_number,
                question_key=item.question_key,
                sort_order=order,
                stem_markdown=item.stem_markdown,
                answer_markdown=item.answer_markdown,
                analysis_markdown=item.analysis_markdown,
                difficulty=item.difficulty,
            )
            session.add(generated)
            await session.flush()
            points = await resolve_knowledge_points(
                session, student_subject.subject_id, item.knowledge_points
            )
            session.add_all(
                [
                    GeneratedQuestionKnowledgePoint(
                        generated_question_id=generated.id, knowledge_point_id=point.id
                    )
                    for point in points
                ]
            )
    question_set.status = target
    version.status = target
    question_set.version += 1
    session.add(
        AuditLog(
            actor_user_id=user_id,
            action=f"QUESTION_SET_{target.value}",
            entity_type="GeneratedQuestionSet",
            entity_id=str(question_set.id),
            change_summary={"reason": payload.reason, "version": version.version_number},
        )
    )
    await session.commit()
    return await question_set_response(session, question_set)


@router.post("/question-sets/{set_id}/submit", response_model=QuestionSetResponse)
async def submit_question_set(
    set_id: uuid.UUID, payload: ReviewAction, user: CsrfUserDep, session: SessionDep
) -> QuestionSetResponse:
    item = await owned_question_set(session, set_id, user.id, for_update=True)
    return await transition_question_set(
        session, item, user.id, payload, ReviewStatus.PENDING_REVIEW
    )


@router.post("/question-sets/{set_id}/approve", response_model=QuestionSetResponse)
async def approve_question_set(
    set_id: uuid.UUID, payload: ReviewAction, user: CsrfUserDep, session: SessionDep
) -> QuestionSetResponse:
    item = await owned_question_set(session, set_id, user.id, for_update=True)
    return await transition_question_set(session, item, user.id, payload, ReviewStatus.APPROVED)


@router.post("/question-sets/{set_id}/reject", response_model=QuestionSetResponse)
async def reject_question_set(
    set_id: uuid.UUID, payload: ReviewAction, user: CsrfUserDep, session: SessionDep
) -> QuestionSetResponse:
    item = await owned_question_set(session, set_id, user.id, for_update=True)
    return await transition_question_set(session, item, user.id, payload, ReviewStatus.REJECTED)
