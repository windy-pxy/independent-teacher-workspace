from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.auth import require_csrf, require_user
from teacher_workspace.config import get_settings
from teacher_workspace.db import get_session
from teacher_workspace.models import (
    AuditLog,
    Lesson,
    LessonPlanItem,
    LessonStatus,
    PlanItemStatus,
    Student,
    StudentSubject,
    Subject,
    TeachingPlan,
    TeachingPlanItem,
    TeachingPlanRevision,
    User,
    utc_now,
)
from teacher_workspace.phase1_schemas import (
    ArchiveRequest,
    DashboardProgress,
    DashboardResponse,
    LessonCancel,
    LessonComplete,
    LessonCreate,
    LessonReschedule,
    LessonResponse,
    LessonUpdate,
    PlanCreate,
    PlanItemCreate,
    PlanItemResponse,
    PlanItemUpdate,
    PlanResponse,
    PlanRevisionResponse,
    PlanUpdate,
    StudentCreate,
    StudentResponse,
    StudentSubjectCreate,
    StudentSubjectResponse,
    StudentSubjectUpdate,
    StudentUpdate,
    SubjectCreate,
    SubjectResponse,
    SubjectUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["phase-1"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[User, Depends(require_user)]
CsrfUserDep = Annotated[User, Depends(require_csrf)]


def problem(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def audit(
    session: AsyncSession,
    request: Request,
    user: User,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    summary: dict[str, Any],
) -> None:
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            change_summary=summary,
            request_id=getattr(request.state, "request_id", None),
        )
    )


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise problem("VERSION_CONFLICT", "记录已被其他操作更新，请刷新后重试", 409)


async def owned_student(session: AsyncSession, user: User, entity_id: uuid.UUID) -> Student:
    entity = await session.scalar(
        select(Student).where(Student.id == entity_id, Student.owner_user_id == user.id)
    )
    if entity is None:
        raise problem("STUDENT_NOT_FOUND", "学生不存在", 404)
    return entity


async def owned_subject(session: AsyncSession, user: User, entity_id: uuid.UUID) -> Subject:
    entity = await session.scalar(
        select(Subject).where(Subject.id == entity_id, Subject.owner_user_id == user.id)
    )
    if entity is None:
        raise problem("SUBJECT_NOT_FOUND", "学科不存在", 404)
    return entity


async def owned_student_subject(
    session: AsyncSession, user: User, entity_id: uuid.UUID
) -> StudentSubject:
    entity = await session.scalar(
        select(StudentSubject)
        .join(Student, Student.id == StudentSubject.student_id)
        .join(Subject, Subject.id == StudentSubject.subject_id)
        .where(
            StudentSubject.id == entity_id,
            Student.owner_user_id == user.id,
            Subject.owner_user_id == user.id,
        )
    )
    if entity is None:
        raise problem("STUDENT_SUBJECT_NOT_FOUND", "学生学科档案不存在", 404)
    return entity


async def owned_plan(session: AsyncSession, user: User, entity_id: uuid.UUID) -> TeachingPlan:
    entity = await session.scalar(
        select(TeachingPlan)
        .join(StudentSubject, StudentSubject.id == TeachingPlan.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(TeachingPlan.id == entity_id, Student.owner_user_id == user.id)
    )
    if entity is None:
        raise problem("PLAN_NOT_FOUND", "教学计划不存在", 404)
    return entity


async def owned_plan_item(
    session: AsyncSession, user: User, entity_id: uuid.UUID
) -> TeachingPlanItem:
    entity = await session.scalar(
        select(TeachingPlanItem)
        .join(TeachingPlan, TeachingPlan.id == TeachingPlanItem.plan_id)
        .join(StudentSubject, StudentSubject.id == TeachingPlan.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(TeachingPlanItem.id == entity_id, Student.owner_user_id == user.id)
    )
    if entity is None:
        raise problem("PLAN_ITEM_NOT_FOUND", "计划条目不存在", 404)
    return entity


async def owned_lesson(session: AsyncSession, user: User, entity_id: uuid.UUID) -> Lesson:
    entity = await session.scalar(
        select(Lesson)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(Lesson.id == entity_id, Student.owner_user_id == user.id)
    )
    if entity is None:
        raise problem("LESSON_NOT_FOUND", "课程不存在", 404)
    return entity


def student_response(entity: Student) -> StudentResponse:
    return StudentResponse(
        id=entity.id,
        display_name=entity.display_name,
        grade=entity.grade,
        region=entity.region,
        school=entity.school,
        learning_characteristics=entity.learning_characteristics,
        guardian_requirements=entity.guardian_requirements,
        notes=entity.notes,
        version=entity.version,
        archived_at=entity.archived_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def subject_response(entity: Subject) -> SubjectResponse:
    return SubjectResponse(
        id=entity.id,
        name=entity.name,
        description=entity.description,
        version=entity.version,
        archived_at=entity.archived_at,
    )


async def student_subject_response(
    session: AsyncSession, entity: StudentSubject
) -> StudentSubjectResponse:
    student = await session.get(Student, entity.student_id)
    subject = await session.get(Subject, entity.subject_id)
    if student is None or subject is None:
        raise problem("RELATED_RECORD_MISSING", "关联的学生或学科不存在", 409)
    return StudentSubjectResponse(
        id=entity.id,
        student_id=entity.student_id,
        student_name=student.display_name,
        subject_id=entity.subject_id,
        subject_name=subject.name,
        textbook_version=entity.textbook_version,
        current_foundation=entity.current_foundation,
        overall_goal=entity.overall_goal,
        stage_goal=entity.stage_goal,
        teaching_requirements=entity.teaching_requirements,
        attention_notes=entity.attention_notes,
        version=entity.version,
        archived_at=entity.archived_at,
    )


def plan_item_response(entity: TeachingPlanItem) -> PlanItemResponse:
    return PlanItemResponse(
        id=entity.id,
        plan_id=entity.plan_id,
        parent_id=entity.parent_id,
        item_type=entity.item_type,
        title=entity.title,
        description=entity.description,
        sort_order=entity.sort_order,
        estimated_minutes=entity.estimated_minutes,
        actual_minutes=entity.actual_minutes,
        status=entity.status,
        progress_notes=entity.progress_notes,
        version=entity.version,
    )


async def plan_response(session: AsyncSession, entity: TeachingPlan) -> PlanResponse:
    student_subject = await session.get(StudentSubject, entity.student_subject_id)
    if student_subject is None:
        raise problem("RELATED_RECORD_MISSING", "计划关联档案不存在", 409)
    student = await session.get(Student, student_subject.student_id)
    subject = await session.get(Subject, student_subject.subject_id)
    if student is None or subject is None:
        raise problem("RELATED_RECORD_MISSING", "计划关联学生或学科不存在", 409)
    items = list(
        (
            await session.scalars(
                select(TeachingPlanItem)
                .where(
                    TeachingPlanItem.plan_id == entity.id,
                    TeachingPlanItem.archived_at.is_(None),
                )
                .order_by(TeachingPlanItem.sort_order, TeachingPlanItem.created_at)
            )
        ).all()
    )
    return PlanResponse(
        id=entity.id,
        student_subject_id=entity.student_subject_id,
        student_name=student.display_name,
        subject_name=subject.name,
        name=entity.name,
        description=entity.description,
        version=entity.version,
        archived_at=entity.archived_at,
        items=[plan_item_response(item) for item in items],
    )


async def create_plan_revision(
    session: AsyncSession, plan: TeachingPlan, user: User, reason: str
) -> None:
    items = list(
        (
            await session.scalars(
                select(TeachingPlanItem)
                .where(TeachingPlanItem.plan_id == plan.id)
                .order_by(TeachingPlanItem.sort_order, TeachingPlanItem.created_at)
            )
        ).all()
    )
    snapshot = {
        "plan": {"name": plan.name, "description": plan.description, "version": plan.version},
        "items": [
            {
                "id": str(item.id),
                "parent_id": str(item.parent_id) if item.parent_id else None,
                "item_type": item.item_type.value,
                "title": item.title,
                "description": item.description,
                "sort_order": item.sort_order,
                "estimated_minutes": item.estimated_minutes,
                "actual_minutes": item.actual_minutes,
                "status": item.status.value,
                "progress_notes": item.progress_notes,
                "archived_at": item.archived_at.isoformat() if item.archived_at else None,
            }
            for item in items
        ],
    }
    session.add(
        TeachingPlanRevision(
            plan_id=plan.id,
            version_number=plan.version,
            adjustment_reason=reason.strip(),
            snapshot=snapshot,
            created_by_user_id=user.id,
        )
    )


async def lesson_response(session: AsyncSession, entity: Lesson) -> LessonResponse:
    student_subject = await session.get(StudentSubject, entity.student_subject_id)
    if student_subject is None:
        raise problem("RELATED_RECORD_MISSING", "课程关联档案不存在", 409)
    student = await session.get(Student, student_subject.student_id)
    subject = await session.get(Subject, student_subject.subject_id)
    plan_item_ids = list(
        (
            await session.scalars(
                select(LessonPlanItem.plan_item_id).where(LessonPlanItem.lesson_id == entity.id)
            )
        ).all()
    )
    if student is None or subject is None:
        raise problem("RELATED_RECORD_MISSING", "课程关联学生或学科不存在", 409)
    return LessonResponse(
        id=entity.id,
        student_subject_id=entity.student_subject_id,
        student_name=student.display_name,
        subject_name=subject.name,
        scheduled_start=entity.scheduled_start,
        planned_minutes=entity.planned_minutes,
        actual_minutes=entity.actual_minutes,
        lesson_type=entity.lesson_type,
        theme=entity.theme,
        special_requirements=entity.special_requirements,
        status=entity.status,
        rescheduled_from_lesson_id=entity.rescheduled_from_lesson_id,
        makeup_for_lesson_id=entity.makeup_for_lesson_id,
        cancellation_reason=entity.cancellation_reason,
        plan_item_ids=plan_item_ids,
        version=entity.version,
    )


@router.get("/students", response_model=list[StudentResponse])
async def list_students(
    user: UserDep,
    session: SessionDep,
    include_archived: bool = False,
) -> list[StudentResponse]:
    statement = select(Student).where(Student.owner_user_id == user.id)
    if not include_archived:
        statement = statement.where(Student.archived_at.is_(None))
    rows = (await session.scalars(statement.order_by(Student.display_name))).all()
    return [student_response(row) for row in rows]


@router.post("/students", response_model=StudentResponse, status_code=201)
async def create_student(
    payload: StudentCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> StudentResponse:
    entity = Student(owner_user_id=user.id, **payload.model_dump())
    session.add(entity)
    await session.flush()
    audit(
        session,
        request,
        user,
        "STUDENT_CREATED",
        "Student",
        entity.id,
        {"display_name": entity.display_name},
    )
    await session.commit()
    await session.refresh(entity)
    return student_response(entity)


@router.get("/students/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: uuid.UUID,
    user: UserDep,
    session: SessionDep,
) -> StudentResponse:
    return student_response(await owned_student(session, user, student_id))


@router.put("/students/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: uuid.UUID,
    payload: StudentUpdate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> StudentResponse:
    entity = await owned_student(session, user, student_id)
    check_version(entity.version, payload.version)
    planned_lessons = int(
        await session.scalar(
            select(func.count())
            .select_from(Lesson)
            .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
            .where(
                StudentSubject.student_id == entity.id,
                Lesson.status == LessonStatus.PLANNED,
                Lesson.archived_at.is_(None),
            )
        )
        or 0
    )
    if planned_lessons:
        raise problem("STUDENT_HAS_PLANNED_LESSONS", "请先取消或调走该学生计划中的课程", 409)
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(entity, key, value)
    entity.version += 1
    audit(
        session, request, user, "STUDENT_UPDATED", "Student", entity.id, {"version": entity.version}
    )
    await session.commit()
    await session.refresh(entity)
    return student_response(entity)


@router.post("/students/{student_id}/archive", response_model=StudentResponse)
async def archive_student(
    student_id: uuid.UUID,
    payload: ArchiveRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> StudentResponse:
    entity = await owned_student(session, user, student_id)
    check_version(entity.version, payload.version)
    entity.archived_at = utc_now()
    entity.version += 1
    audit(
        session,
        request,
        user,
        "STUDENT_ARCHIVED",
        "Student",
        entity.id,
        {"version": entity.version, "reason": payload.reason},
    )
    await session.commit()
    await session.refresh(entity)
    return student_response(entity)


@router.get("/subjects", response_model=list[SubjectResponse])
async def list_subjects(
    user: UserDep,
    session: SessionDep,
    include_archived: bool = False,
) -> list[SubjectResponse]:
    statement = select(Subject).where(Subject.owner_user_id == user.id)
    if not include_archived:
        statement = statement.where(Subject.archived_at.is_(None))
    rows = (await session.scalars(statement.order_by(Subject.name))).all()
    return [subject_response(row) for row in rows]


@router.post("/subjects", response_model=SubjectResponse, status_code=201)
async def create_subject(
    payload: SubjectCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> SubjectResponse:
    name = payload.name.strip()
    entity = Subject(
        owner_user_id=user.id,
        name=name,
        normalized_name=name.casefold(),
        description=clean(payload.description),
    )
    session.add(entity)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise problem("SUBJECT_EXISTS", "该学科已存在", 409) from exc
    audit(session, request, user, "SUBJECT_CREATED", "Subject", entity.id, {"name": name})
    await session.commit()
    await session.refresh(entity)
    return subject_response(entity)


@router.put("/subjects/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: uuid.UUID,
    payload: SubjectUpdate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> SubjectResponse:
    entity = await owned_subject(session, user, subject_id)
    check_version(entity.version, payload.version)
    entity.name = payload.name.strip()
    entity.normalized_name = entity.name.casefold()
    entity.description = clean(payload.description)
    entity.version += 1
    audit(
        session, request, user, "SUBJECT_UPDATED", "Subject", entity.id, {"version": entity.version}
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise problem("SUBJECT_EXISTS", "该学科名称已存在", 409) from exc
    await session.refresh(entity)
    return subject_response(entity)


@router.post("/subjects/{subject_id}/archive", response_model=SubjectResponse)
async def archive_subject(
    subject_id: uuid.UUID,
    payload: ArchiveRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> SubjectResponse:
    entity = await owned_subject(session, user, subject_id)
    check_version(entity.version, payload.version)
    active_links = int(
        await session.scalar(
            select(func.count())
            .select_from(StudentSubject)
            .where(
                StudentSubject.subject_id == entity.id,
                StudentSubject.archived_at.is_(None),
            )
        )
        or 0
    )
    if active_links:
        raise problem("SUBJECT_IN_USE", "请先归档该学科下的学生档案", 409)
    entity.archived_at = utc_now()
    entity.version += 1
    audit(
        session,
        request,
        user,
        "SUBJECT_ARCHIVED",
        "Subject",
        entity.id,
        {"version": entity.version, "reason": payload.reason},
    )
    await session.commit()
    await session.refresh(entity)
    return subject_response(entity)


@router.get("/student-subjects", response_model=list[StudentSubjectResponse])
async def list_student_subjects(
    user: UserDep,
    session: SessionDep,
    student_id: uuid.UUID | None = None,
) -> list[StudentSubjectResponse]:
    statement = (
        select(StudentSubject)
        .join(Student, Student.id == StudentSubject.student_id)
        .join(Subject, Subject.id == StudentSubject.subject_id)
        .where(
            Student.owner_user_id == user.id,
            Student.archived_at.is_(None),
            Subject.owner_user_id == user.id,
            StudentSubject.archived_at.is_(None),
        )
    )
    if student_id:
        statement = statement.where(StudentSubject.student_id == student_id)
    rows = (await session.scalars(statement.order_by(Student.display_name, Subject.name))).all()
    return [await student_subject_response(session, row) for row in rows]


@router.post("/student-subjects", response_model=StudentSubjectResponse, status_code=201)
async def create_student_subject(
    payload: StudentSubjectCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> StudentSubjectResponse:
    student = await owned_student(session, user, payload.student_id)
    subject = await owned_subject(session, user, payload.subject_id)
    if student.archived_at or subject.archived_at:
        raise problem("ARCHIVED_RELATED_RECORD", "不能关联已归档的学生或学科", 409)
    entity = StudentSubject(**payload.model_dump())
    session.add(entity)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise problem("STUDENT_SUBJECT_EXISTS", "该学生已关联此学科", 409) from exc
    audit(session, request, user, "STUDENT_SUBJECT_CREATED", "StudentSubject", entity.id, {})
    await session.commit()
    await session.refresh(entity)
    return await student_subject_response(session, entity)


@router.put("/student-subjects/{entity_id}", response_model=StudentSubjectResponse)
async def update_student_subject(
    entity_id: uuid.UUID,
    payload: StudentSubjectUpdate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> StudentSubjectResponse:
    entity = await owned_student_subject(session, user, entity_id)
    check_version(entity.version, payload.version)
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(entity, key, value)
    entity.version += 1
    audit(
        session,
        request,
        user,
        "STUDENT_SUBJECT_UPDATED",
        "StudentSubject",
        entity.id,
        {"version": entity.version},
    )
    await session.commit()
    await session.refresh(entity)
    return await student_subject_response(session, entity)


@router.post("/student-subjects/{entity_id}/archive", response_model=StudentSubjectResponse)
async def archive_student_subject(
    entity_id: uuid.UUID,
    payload: ArchiveRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> StudentSubjectResponse:
    entity = await owned_student_subject(session, user, entity_id)
    check_version(entity.version, payload.version)
    future_lessons = int(
        await session.scalar(
            select(func.count())
            .select_from(Lesson)
            .where(
                Lesson.student_subject_id == entity.id,
                Lesson.status == LessonStatus.PLANNED,
                Lesson.archived_at.is_(None),
            )
        )
        or 0
    )
    if future_lessons:
        raise problem("STUDENT_SUBJECT_HAS_LESSONS", "请先取消或调走计划中的课程", 409)
    entity.archived_at = utc_now()
    entity.version += 1
    audit(
        session,
        request,
        user,
        "STUDENT_SUBJECT_ARCHIVED",
        "StudentSubject",
        entity.id,
        {"version": entity.version, "reason": payload.reason},
    )
    await session.commit()
    await session.refresh(entity)
    return await student_subject_response(session, entity)


@router.get("/teaching-plans", response_model=list[PlanResponse])
async def list_plans(
    user: UserDep,
    session: SessionDep,
    student_subject_id: uuid.UUID | None = None,
) -> list[PlanResponse]:
    statement = (
        select(TeachingPlan)
        .join(StudentSubject, StudentSubject.id == TeachingPlan.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(Student.owner_user_id == user.id, TeachingPlan.archived_at.is_(None))
        .where(Student.archived_at.is_(None))
    )
    if student_subject_id:
        statement = statement.where(TeachingPlan.student_subject_id == student_subject_id)
    rows = (await session.scalars(statement.order_by(TeachingPlan.updated_at.desc()))).all()
    return [await plan_response(session, row) for row in rows]


@router.post("/teaching-plans", response_model=PlanResponse, status_code=201)
async def create_plan(
    payload: PlanCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PlanResponse:
    student_subject = await owned_student_subject(session, user, payload.student_subject_id)
    if student_subject.archived_at:
        raise problem("ARCHIVED_STUDENT_SUBJECT", "不能为已归档档案创建计划", 409)
    entity = TeachingPlan(
        student_subject_id=payload.student_subject_id,
        name=payload.name.strip(),
        description=clean(payload.description),
    )
    session.add(entity)
    await session.flush()
    await create_plan_revision(session, entity, user, "创建教学计划")
    audit(session, request, user, "PLAN_CREATED", "TeachingPlan", entity.id, {"name": entity.name})
    await session.commit()
    await session.refresh(entity)
    return await plan_response(session, entity)


@router.get("/teaching-plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: uuid.UUID,
    user: UserDep,
    session: SessionDep,
) -> PlanResponse:
    return await plan_response(session, await owned_plan(session, user, plan_id))


@router.put("/teaching-plans/{plan_id}", response_model=PlanResponse)
async def update_plan_record(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PlanResponse:
    entity = await owned_plan(session, user, plan_id)
    check_version(entity.version, payload.version)
    entity.name = payload.name.strip()
    entity.description = clean(payload.description)
    entity.version += 1
    await session.flush()
    await create_plan_revision(session, entity, user, payload.adjustment_reason)
    audit(
        session,
        request,
        user,
        "PLAN_UPDATED",
        "TeachingPlan",
        entity.id,
        {"version": entity.version},
    )
    await session.commit()
    await session.refresh(entity)
    return await plan_response(session, entity)


@router.post("/teaching-plans/{plan_id}/archive", response_model=PlanResponse)
async def archive_plan(
    plan_id: uuid.UUID,
    payload: ArchiveRequest,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PlanResponse:
    entity = await owned_plan(session, user, plan_id)
    check_version(entity.version, payload.version)
    entity.archived_at = utc_now()
    entity.version += 1
    await session.flush()
    await create_plan_revision(session, entity, user, payload.reason)
    audit(
        session,
        request,
        user,
        "PLAN_ARCHIVED",
        "TeachingPlan",
        entity.id,
        {"version": entity.version, "reason": payload.reason},
    )
    await session.commit()
    await session.refresh(entity)
    return await plan_response(session, entity)


@router.post("/teaching-plans/{plan_id}/items", response_model=PlanItemResponse, status_code=201)
async def create_plan_item(
    plan_id: uuid.UUID,
    payload: PlanItemCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PlanItemResponse:
    plan = await owned_plan(session, user, plan_id)
    if payload.parent_id:
        parent = await owned_plan_item(session, user, payload.parent_id)
        if parent.plan_id != plan.id:
            raise problem("INVALID_PARENT", "父条目必须属于同一计划", 422)
    entity = TeachingPlanItem(
        plan_id=plan.id,
        parent_id=payload.parent_id,
        item_type=payload.item_type,
        title=payload.title.strip(),
        description=clean(payload.description),
        sort_order=payload.sort_order,
        estimated_minutes=payload.estimated_minutes,
    )
    session.add(entity)
    plan.version += 1
    await session.flush()
    await create_plan_revision(session, plan, user, payload.adjustment_reason)
    audit(
        session,
        request,
        user,
        "PLAN_ITEM_CREATED",
        "TeachingPlanItem",
        entity.id,
        {"plan_id": str(plan.id)},
    )
    await session.commit()
    await session.refresh(entity)
    return plan_item_response(entity)


@router.put("/teaching-plan-items/{item_id}", response_model=PlanItemResponse)
async def update_plan_item(
    item_id: uuid.UUID,
    payload: PlanItemUpdate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PlanItemResponse:
    entity = await owned_plan_item(session, user, item_id)
    check_version(entity.version, payload.version)
    if payload.parent_id == entity.id:
        raise problem("INVALID_PARENT", "条目不能以自身作为父条目", 422)
    if payload.parent_id:
        parent = await owned_plan_item(session, user, payload.parent_id)
        if parent.plan_id != entity.plan_id:
            raise problem("INVALID_PARENT", "父条目必须属于同一计划", 422)
    for key, value in payload.model_dump(exclude={"version", "adjustment_reason"}).items():
        setattr(entity, key, value)
    entity.version += 1
    plan = await owned_plan(session, user, entity.plan_id)
    plan.version += 1
    await session.flush()
    await create_plan_revision(session, plan, user, payload.adjustment_reason)
    audit(
        session,
        request,
        user,
        "PLAN_ITEM_UPDATED",
        "TeachingPlanItem",
        entity.id,
        {"version": entity.version},
    )
    await session.commit()
    await session.refresh(entity)
    return plan_item_response(entity)


@router.get("/teaching-plans/{plan_id}/revisions", response_model=list[PlanRevisionResponse])
async def list_plan_revisions(
    plan_id: uuid.UUID,
    user: UserDep,
    session: SessionDep,
) -> list[PlanRevisionResponse]:
    await owned_plan(session, user, plan_id)
    rows = (
        await session.scalars(
            select(TeachingPlanRevision)
            .where(TeachingPlanRevision.plan_id == plan_id)
            .order_by(TeachingPlanRevision.version_number.desc())
        )
    ).all()
    return [
        PlanRevisionResponse(
            version_number=row.version_number,
            adjustment_reason=row.adjustment_reason,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def validate_plan_item_ids(
    session: AsyncSession,
    user: User,
    student_subject_id: uuid.UUID,
    item_ids: list[uuid.UUID],
) -> list[TeachingPlanItem]:
    if not item_ids:
        return []
    rows = list(
        (
            await session.scalars(
                select(TeachingPlanItem)
                .join(TeachingPlan, TeachingPlan.id == TeachingPlanItem.plan_id)
                .join(StudentSubject, StudentSubject.id == TeachingPlan.student_subject_id)
                .join(Student, Student.id == StudentSubject.student_id)
                .where(
                    TeachingPlanItem.id.in_(item_ids),
                    TeachingPlan.student_subject_id == student_subject_id,
                    Student.owner_user_id == user.id,
                    TeachingPlanItem.archived_at.is_(None),
                )
            )
        ).all()
    )
    if len({row.id for row in rows}) != len(set(item_ids)):
        raise problem("INVALID_PLAN_ITEMS", "存在不属于该学生学科档案的计划条目", 422)
    return rows


@router.get("/lessons", response_model=list[LessonResponse])
async def list_lessons(
    user: UserDep,
    session: SessionDep,
    start: datetime | None = None,
    end: datetime | None = None,
    student_subject_id: uuid.UUID | None = None,
    lesson_status: Annotated[LessonStatus | None, Query(alias="status")] = None,
) -> list[LessonResponse]:
    statement = (
        select(Lesson)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(Student.owner_user_id == user.id, Lesson.archived_at.is_(None))
    )
    if start:
        statement = statement.where(Lesson.scheduled_start >= start)
    if end:
        statement = statement.where(Lesson.scheduled_start < end)
    if student_subject_id:
        statement = statement.where(Lesson.student_subject_id == student_subject_id)
    if lesson_status:
        statement = statement.where(Lesson.status == lesson_status)
    rows = (await session.scalars(statement.order_by(Lesson.scheduled_start))).all()
    return [await lesson_response(session, row) for row in rows]


@router.post("/lessons", response_model=LessonResponse, status_code=201)
async def create_lesson(
    payload: LessonCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    student_subject = await owned_student_subject(session, user, payload.student_subject_id)
    if student_subject.archived_at:
        raise problem("ARCHIVED_STUDENT_SUBJECT", "不能为已归档档案创建课程", 409)
    plan_items = await validate_plan_item_ids(
        session, user, payload.student_subject_id, payload.plan_item_ids
    )
    if payload.makeup_for_lesson_id:
        source = await owned_lesson(session, user, payload.makeup_for_lesson_id)
        if source.student_subject_id != payload.student_subject_id:
            raise problem("INVALID_MAKEUP_SOURCE", "补课必须属于同一学生和学科", 422)
    entity = Lesson(
        student_subject_id=payload.student_subject_id,
        scheduled_start=payload.scheduled_start.astimezone(UTC),
        planned_minutes=payload.planned_minutes,
        lesson_type=payload.lesson_type,
        theme=payload.theme.strip(),
        special_requirements=clean(payload.special_requirements),
        makeup_for_lesson_id=payload.makeup_for_lesson_id,
    )
    session.add(entity)
    await session.flush()
    session.add_all(
        [LessonPlanItem(lesson_id=entity.id, plan_item_id=item.id) for item in plan_items]
    )
    audit(
        session,
        request,
        user,
        "LESSON_CREATED",
        "Lesson",
        entity.id,
        {"scheduled_start": entity.scheduled_start.isoformat()},
    )
    await session.commit()
    await session.refresh(entity)
    return await lesson_response(session, entity)


@router.get("/lessons/{lesson_id}", response_model=LessonResponse)
async def get_lesson(
    lesson_id: uuid.UUID,
    user: UserDep,
    session: SessionDep,
) -> LessonResponse:
    return await lesson_response(session, await owned_lesson(session, user, lesson_id))


@router.put("/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: uuid.UUID,
    payload: LessonUpdate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    entity = await owned_lesson(session, user, lesson_id)
    check_version(entity.version, payload.version)
    if entity.status != LessonStatus.PLANNED:
        raise problem("LESSON_NOT_EDITABLE", "只有计划中的课程可以编辑", 409)
    plan_items = await validate_plan_item_ids(
        session, user, entity.student_subject_id, payload.plan_item_ids
    )
    entity.scheduled_start = payload.scheduled_start.astimezone(UTC)
    entity.planned_minutes = payload.planned_minutes
    entity.lesson_type = payload.lesson_type
    entity.theme = payload.theme.strip()
    entity.special_requirements = clean(payload.special_requirements)
    entity.version += 1
    existing = list(
        (
            await session.scalars(
                select(LessonPlanItem).where(LessonPlanItem.lesson_id == entity.id)
            )
        ).all()
    )
    for row in existing:
        await session.delete(row)
    session.add_all(
        [LessonPlanItem(lesson_id=entity.id, plan_item_id=item.id) for item in plan_items]
    )
    audit(
        session, request, user, "LESSON_UPDATED", "Lesson", entity.id, {"version": entity.version}
    )
    await session.commit()
    await session.refresh(entity)
    return await lesson_response(session, entity)


@router.post("/lessons/{lesson_id}/complete", response_model=LessonResponse)
async def complete_lesson(
    lesson_id: uuid.UUID,
    payload: LessonComplete,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    entity = await owned_lesson(session, user, lesson_id)
    if entity.status != LessonStatus.PLANNED:
        raise problem("INVALID_LESSON_TRANSITION", "只有计划中的课程可以标记完成", 409)
    update_ids = [item.plan_item_id for item in payload.progress_updates]
    plan_items = await validate_plan_item_ids(session, user, entity.student_subject_id, update_ids)
    item_map = {item.id: item for item in plan_items}
    changed_plans: set[uuid.UUID] = set()
    for update_data in payload.progress_updates:
        item = item_map[update_data.plan_item_id]
        item.status = update_data.status
        item.actual_minutes += update_data.actual_minutes_delta
        if update_data.progress_notes is not None:
            item.progress_notes = clean(update_data.progress_notes)
        item.version += 1
        changed_plans.add(item.plan_id)
    entity.status = LessonStatus.COMPLETED
    entity.actual_minutes = payload.actual_minutes
    entity.completed_at = utc_now()
    entity.version += 1
    await session.flush()
    for plan_id in changed_plans:
        plan = await owned_plan(session, user, plan_id)
        plan.version += 1
        await session.flush()
        await create_plan_revision(session, plan, user, payload.adjustment_reason)
    audit(
        session,
        request,
        user,
        "LESSON_COMPLETED",
        "Lesson",
        entity.id,
        {"actual_minutes": entity.actual_minutes, "updated_plan_items": len(update_ids)},
    )
    await session.commit()
    await session.refresh(entity)
    return await lesson_response(session, entity)


@router.post("/lessons/{lesson_id}/cancel", response_model=LessonResponse)
async def cancel_lesson(
    lesson_id: uuid.UUID,
    payload: LessonCancel,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    entity = await owned_lesson(session, user, lesson_id)
    check_version(entity.version, payload.version)
    if entity.status != LessonStatus.PLANNED:
        raise problem("INVALID_LESSON_TRANSITION", "只有计划中的课程可以取消", 409)
    entity.status = LessonStatus.CANCELED
    entity.cancellation_reason = payload.reason.strip()
    entity.version += 1
    audit(
        session, request, user, "LESSON_CANCELED", "Lesson", entity.id, {"reason": payload.reason}
    )
    await session.commit()
    await session.refresh(entity)
    return await lesson_response(session, entity)


@router.post("/lessons/{lesson_id}/reschedule", response_model=LessonResponse, status_code=201)
async def reschedule_lesson(
    lesson_id: uuid.UUID,
    payload: LessonReschedule,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    original = await owned_lesson(session, user, lesson_id)
    check_version(original.version, payload.version)
    if original.status != LessonStatus.PLANNED:
        raise problem("INVALID_LESSON_TRANSITION", "只有计划中的课程可以调课", 409)
    plan_item_ids = list(
        (
            await session.scalars(
                select(LessonPlanItem.plan_item_id).where(LessonPlanItem.lesson_id == original.id)
            )
        ).all()
    )
    replacement = Lesson(
        student_subject_id=original.student_subject_id,
        scheduled_start=payload.scheduled_start.astimezone(UTC),
        planned_minutes=payload.planned_minutes or original.planned_minutes,
        lesson_type=original.lesson_type,
        theme=original.theme,
        special_requirements=original.special_requirements,
        rescheduled_from_lesson_id=original.id,
    )
    session.add(replacement)
    original.status = LessonStatus.RESCHEDULED
    original.cancellation_reason = payload.reason.strip()
    original.version += 1
    await session.flush()
    session.add_all(
        [
            LessonPlanItem(lesson_id=replacement.id, plan_item_id=item_id)
            for item_id in plan_item_ids
        ]
    )
    audit(
        session,
        request,
        user,
        "LESSON_RESCHEDULED",
        "Lesson",
        original.id,
        {"replacement_id": str(replacement.id), "reason": payload.reason},
    )
    await session.commit()
    await session.refresh(replacement)
    return await lesson_response(session, replacement)


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    user: UserDep,
    session: SessionDep,
) -> DashboardResponse:
    settings = get_settings()
    if settings.app_timezone != "Asia/Shanghai":
        raise problem("UNSUPPORTED_TIMEZONE", "Phase 1 仪表盘仅支持 Asia/Shanghai", 500)
    local_now = datetime.now(UTC) + timedelta(hours=8)
    day_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = (day_start_local - timedelta(hours=8)).replace(tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    seven_day_end = day_start + timedelta(days=8)
    week_start = day_start - timedelta(days=day_start_local.weekday())
    month_start_local = day_start_local.replace(day=1)
    month_start = (month_start_local - timedelta(hours=8)).replace(tzinfo=UTC)

    base = (
        select(Lesson)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .where(Student.owner_user_id == user.id, Lesson.archived_at.is_(None))
    )
    today_rows = (
        await session.scalars(
            base.where(
                Lesson.scheduled_start >= day_start, Lesson.scheduled_start < day_end
            ).order_by(Lesson.scheduled_start)
        )
    ).all()
    next_rows = (
        await session.scalars(
            base.where(
                Lesson.scheduled_start >= day_end,
                Lesson.scheduled_start < seven_day_end,
                Lesson.status == LessonStatus.PLANNED,
            ).order_by(Lesson.scheduled_start)
        )
    ).all()
    planned_this_week = int(
        await session.scalar(
            select(func.count())
            .select_from(Lesson)
            .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
            .join(Student, Student.id == StudentSubject.student_id)
            .where(
                Student.owner_user_id == user.id,
                Lesson.scheduled_start >= week_start,
                Lesson.scheduled_start < week_start + timedelta(days=7),
                Lesson.status != LessonStatus.CANCELED,
            )
        )
        or 0
    )
    completed_this_month = int(
        await session.scalar(
            select(func.count())
            .select_from(Lesson)
            .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
            .join(Student, Student.id == StudentSubject.student_id)
            .where(
                Student.owner_user_id == user.id,
                Lesson.scheduled_start >= month_start,
                Lesson.status == LessonStatus.COMPLETED,
            )
        )
        or 0
    )
    student_subjects = (
        await session.scalars(
            select(StudentSubject)
            .join(Student, Student.id == StudentSubject.student_id)
            .where(
                Student.owner_user_id == user.id,
                Student.archived_at.is_(None),
                StudentSubject.archived_at.is_(None),
            )
        )
    ).all()
    progress: list[DashboardProgress] = []
    for student_subject in student_subjects:
        student = await session.get(Student, student_subject.student_id)
        subject = await session.get(Subject, student_subject.subject_id)
        counts = (
            await session.execute(
                select(
                    func.count(TeachingPlanItem.id),
                    func.count(TeachingPlanItem.id).filter(
                        TeachingPlanItem.status == PlanItemStatus.COMPLETED
                    ),
                )
                .join(TeachingPlan, TeachingPlan.id == TeachingPlanItem.plan_id)
                .where(
                    TeachingPlan.student_subject_id == student_subject.id,
                    TeachingPlan.archived_at.is_(None),
                    TeachingPlanItem.archived_at.is_(None),
                )
            )
        ).one()
        total, completed = int(counts[0]), int(counts[1])
        if student and subject:
            progress.append(
                DashboardProgress(
                    student_subject_id=student_subject.id,
                    student_name=student.display_name,
                    subject_name=subject.name,
                    completed_items=completed,
                    total_items=total,
                    percent=round(completed * 100 / total) if total else 0,
                )
            )
    return DashboardResponse(
        today=[await lesson_response(session, row) for row in today_rows],
        next_seven_days=[await lesson_response(session, row) for row in next_rows],
        progress=progress,
        planned_this_week=planned_this_week,
        completed_this_month=completed_this_month,
    )
