from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.models import (
    Lesson,
    LessonStatus,
    Payment,
    PaymentAllocation,
    Student,
    StudentSubject,
    Subject,
)
from teacher_workspace.phase5_schemas import LessonBillingResponse, PaymentStatus


def calculated_receivable_cents(unit_price_cents: int, minutes: int) -> int:
    """Round a non-negative hourly rate to the nearest cent using half-up."""
    if unit_price_cents < 0 or minutes < 0:
        raise ValueError("Pricing inputs must be non-negative")
    return (unit_price_cents * minutes + 30) // 60


def refresh_lesson_receivable(lesson: Lesson) -> None:
    if lesson.receivable_is_overridden:
        return
    if lesson.status in {LessonStatus.CANCELED, LessonStatus.RESCHEDULED}:
        lesson.receivable_cents = 0
        return
    minutes = (
        lesson.actual_minutes
        if lesson.status == LessonStatus.COMPLETED and lesson.actual_minutes is not None
        else lesson.planned_minutes
    )
    lesson.receivable_cents = calculated_receivable_cents(
        lesson.unit_price_cents, minutes
    )


def payment_status(receivable_cents: int, allocated_cents: int) -> PaymentStatus:
    if allocated_cents > receivable_cents:
        return "OVERPAID"
    if allocated_cents == receivable_cents:
        return "PAID"
    if allocated_cents == 0:
        return "UNPAID"
    return "PARTIAL"


@dataclass(frozen=True)
class BillingRow:
    response: LessonBillingResponse
    student_id: uuid.UUID


async def active_allocation_map(
    session: AsyncSession, lesson_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not lesson_ids:
        return {}
    rows = (
        await session.execute(
            select(
                PaymentAllocation.lesson_id,
                func.coalesce(func.sum(PaymentAllocation.amount_cents), 0),
            )
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(
                PaymentAllocation.lesson_id.in_(lesson_ids),
                Payment.voided_at.is_(None),
            )
            .group_by(PaymentAllocation.lesson_id)
        )
    ).all()
    return {row[0]: int(row[1]) for row in rows}


async def billing_rows(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    *,
    student_subject_id: uuid.UUID | None = None,
) -> list[BillingRow]:
    statement = (
        select(Lesson, StudentSubject, Student, Subject)
        .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
        .join(Student, Student.id == StudentSubject.student_id)
        .join(Subject, Subject.id == StudentSubject.subject_id)
        .where(
            Student.owner_user_id == owner_user_id,
            Subject.owner_user_id == owner_user_id,
            Lesson.scheduled_start >= date_from,
            Lesson.scheduled_start < date_to,
            Lesson.archived_at.is_(None),
        )
        .order_by(Lesson.scheduled_start)
    )
    if student_subject_id is not None:
        statement = statement.where(Lesson.student_subject_id == student_subject_id)
    raw_rows = (await session.execute(statement)).all()
    allocations = await active_allocation_map(
        session, [row[0].id for row in raw_rows]
    )
    result: list[BillingRow] = []
    for lesson, student_subject, student, subject in raw_rows:
        allocated = allocations.get(lesson.id, 0)
        result.append(
            BillingRow(
                student_id=student.id,
                response=LessonBillingResponse(
                    lesson_id=lesson.id,
                    student_subject_id=student_subject.id,
                    student_name=student.display_name,
                    subject_name=subject.name,
                    scheduled_start=lesson.scheduled_start,
                    lesson_status=lesson.status.value,
                    theme=lesson.theme,
                    planned_minutes=lesson.planned_minutes,
                    actual_minutes=lesson.actual_minutes,
                    unit_price_cents=lesson.unit_price_cents,
                    receivable_cents=lesson.receivable_cents,
                    receivable_is_overridden=lesson.receivable_is_overridden,
                    receivable_override_reason=lesson.receivable_override_reason,
                    allocated_cents=allocated,
                    outstanding_cents=max(lesson.receivable_cents - allocated, 0),
                    payment_status=payment_status(
                        lesson.receivable_cents, allocated
                    ),
                    version=lesson.version,
                ),
            )
        )
    return result
