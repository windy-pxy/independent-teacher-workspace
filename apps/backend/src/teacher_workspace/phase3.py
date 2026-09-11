from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.auth import AIUserDep, CsrfUserDep, UserDep
from teacher_workspace.config import get_settings
from teacher_workspace.db import get_session
from teacher_workspace.feedback_contract import LessonFeedbackContent
from teacher_workspace.models import (
    AIJob,
    AIJobStatus,
    AuditLog,
    FeedbackVersionSource,
    KnowledgePoint,
    Lesson,
    LessonFeedback,
    LessonFeedbackVersion,
    LessonStatus,
    MasteryEvidence,
    MasteryLevel,
    PlanItemStatus,
    ReviewStatus,
    Student,
    StudentMastery,
    StudentSubject,
    TeachingPlan,
    TeachingPlanItem,
)
from teacher_workspace.phase1 import create_plan_revision, owned_lesson
from teacher_workspace.phase3_schemas import (
    FeedbackAIJobResponse,
    FeedbackOrganizeRequest,
    FeedbackReviewRequest,
    FeedbackSaveRequest,
    FeedbackVersionResponse,
    LessonFeedbackResponse,
    MasteryResponse,
    QuickFeedbackInput,
)
from teacher_workspace.phase3_service import (
    ensure_default_feedback_template,
    normalize_knowledge_name,
)
from teacher_workspace.providers.ai import configured_ai_model

router = APIRouter(prefix="/api/v1", tags=["lesson-feedback"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise api_error(409, "VERSION_CONFLICT", "记录已被其他操作更新，请刷新后重试")


def split_keywords(value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    return [item.strip() for item in re.split(r"[\n,，;；]+", value) if item.strip()]


def quick_content(payload: QuickFeedbackInput) -> LessonFeedbackContent:
    completed = split_keywords(payload.actual_completed_content)
    unfinished = split_keywords(payload.unfinished_content)
    strong = split_keywords(payload.strong_knowledge_points)
    weak = split_keywords(payload.weak_knowledge_points)
    mistakes = split_keywords(payload.typical_mistakes)
    summary_parts = []
    if completed:
        summary_parts.append("已完成：" + "、".join(completed))
    if unfinished:
        summary_parts.append("未完成：" + "、".join(unfinished))
    if weak:
        summary_parts.append("薄弱点：" + "、".join(weak))
    return LessonFeedbackContent(
        schema_version="1.0",
        actual_completed_content=completed,
        unfinished_content=unfinished,
        student_performance=payload.student_performance or "未记录",
        strong_knowledge_points=strong,
        weak_knowledge_points=weak,
        typical_mistakes=mistakes,
        homework_completion=payload.homework_completion or "未记录",
        next_lesson_special_arrangement=(
            payload.next_lesson_special_arrangement or "未记录"
        ),
        structured_summary="；".join(summary_parts) or "等待 AI 整理或教师补充。",
        next_lesson_suggestion=(
            payload.next_lesson_special_arrangement or "等待 AI 整理或教师补充。"
        ),
        plan_progress_updates=[],
        mastery_updates=[],
    )


async def owned_feedback(
    session: AsyncSession,
    feedback_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> LessonFeedback:
    statement = (
        select(LessonFeedback)
        .join(Lesson, Lesson.id == LessonFeedback.lesson_id)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(LessonFeedback.id == feedback_id, Student.owner_user_id == user_id)
    )
    if for_update:
        statement = statement.with_for_update()
    feedback = await session.scalar(statement)
    if feedback is None:
        raise api_error(404, "FEEDBACK_NOT_FOUND", "课后反馈不存在")
    return feedback


async def feedback_response(
    session: AsyncSession, feedback: LessonFeedback
) -> LessonFeedbackResponse:
    version = await session.scalar(
        select(LessonFeedbackVersion).where(
            LessonFeedbackVersion.feedback_id == feedback.id,
            LessonFeedbackVersion.version_number == feedback.current_version_number,
        )
    )
    if version is None:
        raise api_error(409, "FEEDBACK_VERSION_MISSING", "当前反馈版本不存在")
    return LessonFeedbackResponse(
        id=feedback.id,
        lesson_id=feedback.lesson_id,
        status=feedback.status,
        current_version_number=feedback.current_version_number,
        approved_version_number=feedback.approved_version_number,
        version=feedback.version,
        current_version=FeedbackVersionResponse.model_validate(version),
    )


async def ensure_feedback_targets(
    session: AsyncSession,
    lesson: Lesson,
    content: LessonFeedbackContent,
) -> None:
    plan_ids = {item.plan_item_id for item in content.plan_progress_updates}
    if plan_ids:
        found_plan_ids = set(
            (
                await session.scalars(
                    select(TeachingPlanItem.id)
                    .join(TeachingPlan, TeachingPlan.id == TeachingPlanItem.plan_id)
                    .where(
                        TeachingPlan.student_subject_id == lesson.student_subject_id,
                        TeachingPlanItem.id.in_(plan_ids),
                        TeachingPlanItem.archived_at.is_(None),
                    )
                )
            ).all()
        )
        if found_plan_ids != plan_ids:
            raise api_error(422, "INVALID_PLAN_ITEM", "反馈引用了不可用的计划条目")
    student_subject = await session.get(StudentSubject, lesson.student_subject_id)
    if student_subject is None:
        raise api_error(409, "STUDENT_SUBJECT_MISSING", "课程学科档案不存在")
    point_ids = {
        item.knowledge_point_id
        for item in content.mastery_updates
        if item.knowledge_point_id is not None
    }
    if point_ids:
        found_point_ids = set(
            (
                await session.scalars(
                    select(KnowledgePoint.id).where(
                        KnowledgePoint.subject_id == student_subject.subject_id,
                        KnowledgePoint.id.in_(point_ids),
                        KnowledgePoint.archived_at.is_(None),
                    )
                )
            ).all()
        )
        if found_point_ids != point_ids:
            raise api_error(422, "INVALID_KNOWLEDGE_POINT", "反馈引用了不可用的知识点")


async def active_feedback_job(
    session: AsyncSession, user_id: uuid.UUID, feedback_id: uuid.UUID
) -> bool:
    jobs = (
        await session.scalars(
            select(AIJob).where(
                AIJob.owner_user_id == user_id,
                AIJob.task_type == "lesson_feedback.organize",
                AIJob.status.in_((AIJobStatus.QUEUED, AIJobStatus.RUNNING)),
            )
        )
    ).all()
    return any(job.input_payload.get("feedback_id") == str(feedback_id) for job in jobs)


@router.post(
    "/lessons/{lesson_id}/feedback/drafts",
    response_model=LessonFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback_draft(
    lesson_id: uuid.UUID,
    payload: QuickFeedbackInput,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonFeedbackResponse:
    lesson = await owned_lesson(session, user, lesson_id)
    if lesson.status != LessonStatus.COMPLETED:
        raise api_error(409, "LESSON_NOT_COMPLETED", "课程完成后才能填写课后反馈")
    feedback = await session.scalar(
        select(LessonFeedback).where(LessonFeedback.lesson_id == lesson.id)
    )
    if feedback is None:
        feedback = LessonFeedback(
            lesson_id=lesson.id,
            status=ReviewStatus.DRAFT,
            current_version_number=0,
            created_by_user_id=user.id,
        )
        session.add(feedback)
        await session.flush()
    if feedback.approved_version_number is not None:
        raise api_error(409, "FEEDBACK_ALREADY_APPROVED", "已批准反馈不能再次修改")
    if feedback.status == ReviewStatus.PENDING_REVIEW:
        raise api_error(409, "FEEDBACK_PENDING_REVIEW", "待审核反馈请先驳回再修改")
    if await active_feedback_job(session, user.id, feedback.id):
        raise api_error(409, "FEEDBACK_JOB_IN_PROGRESS", "反馈正在由 AI 整理")
    next_number = int(
        await session.scalar(
            select(func.coalesce(func.max(LessonFeedbackVersion.version_number), 0)).where(
                LessonFeedbackVersion.feedback_id == feedback.id
            )
        )
        or 0
    ) + 1
    if feedback.current_version_number:
        previous = await session.scalar(
            select(LessonFeedbackVersion).where(
                LessonFeedbackVersion.feedback_id == feedback.id,
                LessonFeedbackVersion.version_number
                == feedback.current_version_number,
            )
        )
        if previous is not None:
            previous.status = ReviewStatus.SUPERSEDED
    raw_input = payload.model_dump(mode="json")
    version = LessonFeedbackVersion(
        feedback_id=feedback.id,
        version_number=next_number,
        source=FeedbackVersionSource.QUICK_ENTRY,
        status=ReviewStatus.DRAFT,
        raw_input=raw_input,
        content=quick_content(payload).model_dump(mode="json"),
        change_summary="保存课后关键词",
        created_by_user_id=user.id,
    )
    session.add(version)
    feedback.current_version_number = next_number
    feedback.status = ReviewStatus.DRAFT
    feedback.version += 1
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="LESSON_FEEDBACK_DRAFT_CREATED",
            entity_type="LessonFeedback",
            entity_id=str(feedback.id),
            change_summary={"version_number": next_number},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()
    return await feedback_response(session, feedback)


@router.post(
    "/lesson-feedbacks/{feedback_id}/organize",
    response_model=FeedbackAIJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def organize_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackOrganizeRequest,
    _: AIUserDep,
    user: UserDep,
    session: SessionDep,
) -> FeedbackAIJobResponse:
    feedback = await owned_feedback(session, feedback_id, user.id, for_update=True)
    check_version(feedback.version, payload.version)
    if feedback.approved_version_number is not None:
        raise api_error(409, "FEEDBACK_ALREADY_APPROVED", "已批准反馈不能再次整理")
    if feedback.status not in {ReviewStatus.DRAFT, ReviewStatus.REJECTED}:
        raise api_error(409, "INVALID_REVIEW_STATE", "当前状态不能进行 AI 整理")
    if await active_feedback_job(session, user.id, feedback.id):
        raise api_error(409, "FEEDBACK_JOB_IN_PROGRESS", "反馈正在由 AI 整理")
    _template_entity, template = await ensure_default_feedback_template(session, user.id)
    settings = get_settings()
    job = AIJob(
        owner_user_id=user.id,
        prompt_template_version_id=template.id,
        task_type="lesson_feedback.organize",
        provider=settings.ai_provider,
        model=configured_ai_model(settings),
        idempotency_key=(
            f"lesson-feedback:{feedback.id}:{feedback.current_version_number}:"
            f"{feedback.version + 1}"
        ),
        input_payload={
            "feedback_id": str(feedback.id),
            "source_version_number": feedback.current_version_number,
            "instructions": payload.instructions,
        },
        max_attempts=settings.job_max_attempts,
    )
    session.add(job)
    feedback.version += 1
    await session.commit()
    return FeedbackAIJobResponse.model_validate(job, from_attributes=True)


@router.get(
    "/lessons/{lesson_id}/feedback", response_model=LessonFeedbackResponse
)
async def get_feedback(
    lesson_id: uuid.UUID, user: UserDep, session: SessionDep
) -> LessonFeedbackResponse:
    await owned_lesson(session, user, lesson_id)
    feedback = await session.scalar(
        select(LessonFeedback).where(LessonFeedback.lesson_id == lesson_id)
    )
    if feedback is None:
        raise api_error(404, "FEEDBACK_NOT_FOUND", "该课程尚未填写反馈")
    return await feedback_response(session, feedback)


@router.get(
    "/lesson-feedbacks/{feedback_id}/versions",
    response_model=list[FeedbackVersionResponse],
)
async def list_feedback_versions(
    feedback_id: uuid.UUID, user: UserDep, session: SessionDep
) -> list[FeedbackVersionResponse]:
    await owned_feedback(session, feedback_id, user.id)
    versions = (
        await session.scalars(
            select(LessonFeedbackVersion)
            .where(LessonFeedbackVersion.feedback_id == feedback_id)
            .order_by(LessonFeedbackVersion.version_number.desc())
        )
    ).all()
    return [FeedbackVersionResponse.model_validate(version) for version in versions]


@router.put(
    "/lesson-feedbacks/{feedback_id}", response_model=LessonFeedbackResponse
)
async def save_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackSaveRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonFeedbackResponse:
    feedback = await owned_feedback(session, feedback_id, user.id, for_update=True)
    check_version(feedback.version, payload.version)
    if feedback.approved_version_number is not None:
        raise api_error(409, "FEEDBACK_ALREADY_APPROVED", "已批准反馈不能再次修改")
    if feedback.status not in {ReviewStatus.DRAFT, ReviewStatus.REJECTED}:
        raise api_error(409, "INVALID_REVIEW_STATE", "待审核反馈请先驳回再修改")
    lesson = await session.get(Lesson, feedback.lesson_id)
    if lesson is None:
        raise api_error(409, "LESSON_MISSING", "反馈关联课程不存在")
    await ensure_feedback_targets(session, lesson, payload.content)
    current = await session.scalar(
        select(LessonFeedbackVersion).where(
            LessonFeedbackVersion.feedback_id == feedback.id,
            LessonFeedbackVersion.version_number == feedback.current_version_number,
        )
    )
    if current is None:
        raise api_error(409, "FEEDBACK_VERSION_MISSING", "当前反馈版本不存在")
    next_number = feedback.current_version_number + 1
    version = LessonFeedbackVersion(
        feedback_id=feedback.id,
        version_number=next_number,
        source=FeedbackVersionSource.MANUAL_EDIT,
        status=ReviewStatus.DRAFT,
        raw_input=current.raw_input,
        content=payload.content.model_dump(mode="json"),
        change_summary=payload.change_summary,
        created_by_user_id=user.id,
    )
    current.status = ReviewStatus.SUPERSEDED
    session.add(version)
    feedback.current_version_number = next_number
    feedback.status = ReviewStatus.DRAFT
    feedback.version += 1
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="LESSON_FEEDBACK_VERSION_CREATED",
            entity_type="LessonFeedback",
            entity_id=str(feedback.id),
            change_summary={"version_number": next_number},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()
    return await feedback_response(session, feedback)


async def review_transition(
    session: AsyncSession,
    feedback: LessonFeedback,
    user: UserDep,
    payload: FeedbackReviewRequest,
    target: ReviewStatus,
    request: Request,
) -> LessonFeedbackResponse:
    check_version(feedback.version, payload.version)
    current = await session.scalar(
        select(LessonFeedbackVersion).where(
            LessonFeedbackVersion.feedback_id == feedback.id,
            LessonFeedbackVersion.version_number == feedback.current_version_number,
        )
    )
    if current is None:
        raise api_error(409, "FEEDBACK_VERSION_MISSING", "当前反馈版本不存在")
    if target == ReviewStatus.PENDING_REVIEW and feedback.status not in {
        ReviewStatus.DRAFT,
        ReviewStatus.REJECTED,
    }:
        raise api_error(409, "INVALID_REVIEW_STATE", "当前状态不能提交审核")
    if target in {ReviewStatus.APPROVED, ReviewStatus.REJECTED} and (
        feedback.status != ReviewStatus.PENDING_REVIEW
    ):
        raise api_error(409, "INVALID_REVIEW_STATE", "只有待审核反馈可以执行该操作")
    if target == ReviewStatus.APPROVED:
        if feedback.approved_version_number is not None:
            raise api_error(409, "FEEDBACK_ALREADY_APPROVED", "反馈已经批准")
        lesson = await session.get(Lesson, feedback.lesson_id)
        if lesson is None:
            raise api_error(409, "LESSON_MISSING", "反馈关联课程不存在")
        content = LessonFeedbackContent.model_validate(current.content)
        await ensure_feedback_targets(session, lesson, content)
        changed_plan_ids: set[uuid.UUID] = set()
        for update in content.plan_progress_updates:
            plan_item = await session.scalar(
                select(TeachingPlanItem)
                .where(TeachingPlanItem.id == update.plan_item_id)
                .with_for_update()
            )
            if plan_item is None:
                raise api_error(409, "PLAN_ITEM_MISSING", "计划条目不存在")
            plan_item.status = PlanItemStatus(update.status)
            plan_item.actual_minutes += update.actual_minutes_delta
            plan_item.progress_notes = update.progress_note
            plan_item.version += 1
            changed_plan_ids.add(plan_item.plan_id)
        for plan_id in changed_plan_ids:
            plan = await session.scalar(
                select(TeachingPlan).where(TeachingPlan.id == plan_id).with_for_update()
            )
            if plan is None:
                raise api_error(409, "PLAN_MISSING", "教学计划不存在")
            plan.version += 1
            await session.flush()
            await create_plan_revision(session, plan, user, payload.reason)
        student_subject = await session.get(StudentSubject, lesson.student_subject_id)
        if student_subject is None:
            raise api_error(409, "STUDENT_SUBJECT_MISSING", "课程学科档案不存在")
        for proposal in content.mastery_updates:
            point = None
            if proposal.knowledge_point_id is not None:
                point = await session.get(KnowledgePoint, proposal.knowledge_point_id)
            if point is None:
                normalized = normalize_knowledge_name(proposal.knowledge_point_name)
                point = await session.scalar(
                    select(KnowledgePoint).where(
                        KnowledgePoint.subject_id == student_subject.subject_id,
                        KnowledgePoint.normalized_name == normalized,
                    )
                )
                if point is None:
                    point = KnowledgePoint(
                        subject_id=student_subject.subject_id,
                        name=proposal.knowledge_point_name.strip(),
                        normalized_name=normalized,
                    )
                    session.add(point)
                    await session.flush()
            mastery = await session.scalar(
                select(StudentMastery)
                .where(
                    StudentMastery.student_subject_id == student_subject.id,
                    StudentMastery.knowledge_point_id == point.id,
                )
                .with_for_update()
            )
            previous_level = mastery.level if mastery else MasteryLevel.UNLEARNED
            if mastery is None:
                mastery = StudentMastery(
                    student_subject_id=student_subject.id,
                    knowledge_point_id=point.id,
                    level=proposal.level,
                )
                session.add(mastery)
                await session.flush()
            else:
                mastery.level = proposal.level
                mastery.version += 1
            session.add(
                MasteryEvidence(
                    mastery_id=mastery.id,
                    feedback_version_id=current.id,
                    previous_level=previous_level,
                    new_level=proposal.level,
                    reason=proposal.evidence_note,
                    created_by_user_id=user.id,
                )
            )
        feedback.approved_version_number = current.version_number
    feedback.status = target
    feedback.version += 1
    current.status = target
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action=f"LESSON_FEEDBACK_{target.value}",
            entity_type="LessonFeedback",
            entity_id=str(feedback.id),
            change_summary={
                "reason": payload.reason,
                "version_number": current.version_number,
            },
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()
    return await feedback_response(session, feedback)


@router.post(
    "/lesson-feedbacks/{feedback_id}/submit", response_model=LessonFeedbackResponse
)
async def submit_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackReviewRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonFeedbackResponse:
    feedback = await owned_feedback(session, feedback_id, user.id, for_update=True)
    return await review_transition(
        session, feedback, user, payload, ReviewStatus.PENDING_REVIEW, request
    )


@router.post(
    "/lesson-feedbacks/{feedback_id}/approve", response_model=LessonFeedbackResponse
)
async def approve_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackReviewRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonFeedbackResponse:
    feedback = await owned_feedback(session, feedback_id, user.id, for_update=True)
    return await review_transition(
        session, feedback, user, payload, ReviewStatus.APPROVED, request
    )


@router.post(
    "/lesson-feedbacks/{feedback_id}/reject", response_model=LessonFeedbackResponse
)
async def reject_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackReviewRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonFeedbackResponse:
    feedback = await owned_feedback(session, feedback_id, user.id, for_update=True)
    return await review_transition(
        session, feedback, user, payload, ReviewStatus.REJECTED, request
    )


@router.get(
    "/student-subjects/{student_subject_id}/mastery",
    response_model=list[MasteryResponse],
)
async def list_mastery(
    student_subject_id: uuid.UUID, user: UserDep, session: SessionDep
) -> list[MasteryResponse]:
    owned = await session.scalar(
        select(StudentSubject)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(
            StudentSubject.id == student_subject_id,
            Student.owner_user_id == user.id,
        )
    )
    if owned is None:
        raise api_error(404, "STUDENT_SUBJECT_NOT_FOUND", "学生学科档案不存在")
    rows = (
        await session.execute(
            select(
                StudentMastery,
                KnowledgePoint.name,
                func.count(MasteryEvidence.id),
            )
            .join(
                KnowledgePoint,
                KnowledgePoint.id == StudentMastery.knowledge_point_id,
            )
            .outerjoin(MasteryEvidence, MasteryEvidence.mastery_id == StudentMastery.id)
            .where(StudentMastery.student_subject_id == student_subject_id)
            .group_by(StudentMastery.id, KnowledgePoint.name)
            .order_by(StudentMastery.level, KnowledgePoint.name)
        )
    ).all()
    return [
        MasteryResponse(
            id=mastery.id,
            student_subject_id=mastery.student_subject_id,
            knowledge_point_id=mastery.knowledge_point_id,
            knowledge_point_name=name,
            level=mastery.level,
            version=mastery.version,
            updated_at=mastery.updated_at,
            evidence_count=int(evidence_count),
        )
        for mastery, name, evidence_count in rows
    ]
