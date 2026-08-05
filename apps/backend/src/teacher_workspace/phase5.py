from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.auth import CsrfUserDep, UserDep
from teacher_workspace.db import get_session
from teacher_workspace.models import (
    AuditLog,
    LessonStatus,
    Payment,
    PaymentAllocation,
    User,
)
from teacher_workspace.phase1 import lesson_response, owned_lesson
from teacher_workspace.phase1_schemas import LessonResponse
from teacher_workspace.phase5_schemas import (
    BillingSummaryResponse,
    LessonBillingResponse,
    LessonPricingUpdate,
    LessonReceivableOverride,
    LessonReceivableReset,
    PaymentAllocationCreate,
    PaymentAllocationResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentStatus,
    PaymentVoid,
    StudentBillingSummary,
)
from teacher_workspace.phase5_service import billing_rows, refresh_lesson_receivable

router = APIRouter(prefix="/api/v1", tags=["billing"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise api_error(409, "VERSION_CONFLICT", "记录已更新，请刷新后重试")


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def ensure_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise api_error(422, "TIMEZONE_REQUIRED", f"{field} 必须包含时区")
    return value.astimezone(UTC)


def current_month_period() -> tuple[datetime, datetime]:
    now = datetime.now(SHANGHAI)
    start_local = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_local.month == 12:
        end_local = start_local.replace(year=start_local.year + 1, month=1)
    else:
        end_local = start_local.replace(month=start_local.month + 1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def resolve_period(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime, datetime]:
    default_from, default_to = current_month_period()
    start = ensure_aware(date_from, "date_from") if date_from else default_from
    end = ensure_aware(date_to, "date_to") if date_to else default_to
    if end <= start:
        raise api_error(422, "INVALID_PERIOD", "结束时间必须晚于开始时间")
    if (end - start).days > 3660:
        raise api_error(422, "PERIOD_TOO_LARGE", "单次查询范围不能超过十年")
    return start, end


async def owned_payment(
    session: AsyncSession,
    payment_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Payment:
    statement = select(Payment).where(
        Payment.id == payment_id, Payment.owner_user_id == user_id
    )
    if for_update:
        statement = statement.with_for_update()
    payment = await session.scalar(statement)
    if payment is None:
        raise api_error(404, "PAYMENT_NOT_FOUND", "收款记录不存在")
    return payment


async def payment_response(
    session: AsyncSession, payment: Payment
) -> PaymentResponse:
    allocations = (
        await session.scalars(
            select(PaymentAllocation)
            .where(PaymentAllocation.payment_id == payment.id)
            .order_by(PaymentAllocation.created_at, PaymentAllocation.id)
        )
    ).all()
    allocated = sum(item.amount_cents for item in allocations)
    return PaymentResponse(
        id=payment.id,
        amount_cents=payment.amount_cents,
        paid_at=payment.paid_at,
        method=payment.method,
        reference=payment.reference,
        notes=payment.notes,
        voided_at=payment.voided_at,
        void_reason=payment.void_reason,
        allocated_cents=allocated,
        unallocated_cents=payment.amount_cents - allocated,
        allocations=[
            PaymentAllocationResponse.model_validate(item) for item in allocations
        ],
        version=payment.version,
        created_at=payment.created_at,
    )


def add_audit(
    session: AsyncSession,
    request: Request,
    user: User,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    summary: dict[str, object],
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


@router.put("/lessons/{lesson_id}/pricing", response_model=LessonResponse)
async def update_lesson_pricing(
    lesson_id: uuid.UUID,
    payload: LessonPricingUpdate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    lesson = await owned_lesson(session, user, lesson_id)
    check_version(lesson.version, payload.version)
    if lesson.status == LessonStatus.RESCHEDULED:
        raise api_error(409, "RESCHEDULED_LESSON_NOT_BILLABLE", "已调课原记录不能计费")
    previous = lesson.unit_price_cents
    lesson.unit_price_cents = payload.unit_price_cents
    lesson.receivable_is_overridden = False
    lesson.receivable_override_reason = None
    refresh_lesson_receivable(lesson)
    lesson.version += 1
    add_audit(
        session,
        request,
        user,
        "LESSON_PRICING_UPDATED",
        "Lesson",
        lesson.id,
        {
            "previous_unit_price_cents": previous,
            "unit_price_cents": lesson.unit_price_cents,
            "receivable_cents": lesson.receivable_cents,
            "reason": payload.reason,
        },
    )
    await session.commit()
    return await lesson_response(session, lesson)


@router.post("/lessons/{lesson_id}/receivable-override", response_model=LessonResponse)
async def override_lesson_receivable(
    lesson_id: uuid.UUID,
    payload: LessonReceivableOverride,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    lesson = await owned_lesson(session, user, lesson_id)
    check_version(lesson.version, payload.version)
    if lesson.status == LessonStatus.RESCHEDULED:
        raise api_error(409, "RESCHEDULED_LESSON_NOT_BILLABLE", "已调课原记录不能计费")
    previous = lesson.receivable_cents
    lesson.receivable_cents = payload.receivable_cents
    lesson.receivable_is_overridden = True
    lesson.receivable_override_reason = payload.reason.strip()
    lesson.version += 1
    add_audit(
        session,
        request,
        user,
        "LESSON_RECEIVABLE_OVERRIDDEN",
        "Lesson",
        lesson.id,
        {
            "previous_receivable_cents": previous,
            "receivable_cents": lesson.receivable_cents,
            "reason": payload.reason,
        },
    )
    await session.commit()
    return await lesson_response(session, lesson)


@router.post("/lessons/{lesson_id}/receivable-reset", response_model=LessonResponse)
async def reset_lesson_receivable(
    lesson_id: uuid.UUID,
    payload: LessonReceivableReset,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> LessonResponse:
    lesson = await owned_lesson(session, user, lesson_id)
    check_version(lesson.version, payload.version)
    if not lesson.receivable_is_overridden:
        raise api_error(409, "RECEIVABLE_NOT_OVERRIDDEN", "该课程未使用人工应收覆盖")
    previous = lesson.receivable_cents
    lesson.receivable_is_overridden = False
    lesson.receivable_override_reason = None
    refresh_lesson_receivable(lesson)
    lesson.version += 1
    add_audit(
        session,
        request,
        user,
        "LESSON_RECEIVABLE_RESET",
        "Lesson",
        lesson.id,
        {
            "previous_receivable_cents": previous,
            "receivable_cents": lesson.receivable_cents,
            "reason": payload.reason,
        },
    )
    await session.commit()
    return await lesson_response(session, lesson)


@router.get("/billing/lessons", response_model=list[LessonBillingResponse])
async def list_billing_lessons(
    user: UserDep,
    session: SessionDep,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    student_subject_id: uuid.UUID | None = None,
    payment_status_filter: Annotated[
        PaymentStatus | None, Query(alias="payment_status")
    ] = None,
) -> list[LessonBillingResponse]:
    start, end = resolve_period(date_from, date_to)
    rows = await billing_rows(
        session,
        user.id,
        start,
        end,
        student_subject_id=student_subject_id,
    )
    responses = [row.response for row in rows]
    if payment_status_filter:
        responses = [
            item for item in responses if item.payment_status == payment_status_filter
        ]
    return responses


@router.get("/payments", response_model=list[PaymentResponse])
async def list_payments(
    user: UserDep,
    session: SessionDep,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    include_voided: bool = False,
) -> list[PaymentResponse]:
    start, end = resolve_period(date_from, date_to)
    statement = (
        select(Payment)
        .where(
            Payment.owner_user_id == user.id,
            Payment.paid_at >= start,
            Payment.paid_at < end,
        )
        .order_by(Payment.paid_at.desc(), Payment.created_at.desc())
    )
    if not include_voided:
        statement = statement.where(Payment.voided_at.is_(None))
    payments = (await session.scalars(statement)).all()
    return [await payment_response(session, item) for item in payments]


@router.post(
    "/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED
)
async def create_payment(
    payload: PaymentCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PaymentResponse:
    lesson_ids = [item.lesson_id for item in payload.allocations]
    for lesson_id in lesson_ids:
        lesson = await owned_lesson(session, user, lesson_id)
        if lesson.status == LessonStatus.RESCHEDULED:
            raise api_error(422, "INVALID_ALLOCATION_LESSON", "不能向已调课原记录分摊收款")
    payment = Payment(
        owner_user_id=user.id,
        amount_cents=payload.amount_cents,
        paid_at=payload.paid_at.astimezone(UTC),
        method=payload.method.strip(),
        reference=clean(payload.reference),
        notes=clean(payload.notes),
    )
    session.add(payment)
    await session.flush()
    allocations = [
        PaymentAllocation(
            payment_id=payment.id,
            lesson_id=item.lesson_id,
            amount_cents=item.amount_cents,
        )
        for item in payload.allocations
    ]
    session.add_all(allocations)
    add_audit(
        session,
        request,
        user,
        "PAYMENT_CREATED",
        "Payment",
        payment.id,
        {
            "amount_cents": payment.amount_cents,
            "allocation_count": len(allocations),
            "allocated_cents": sum(item.amount_cents for item in allocations),
        },
    )
    await session.commit()
    return await payment_response(session, payment)


@router.post(
    "/payments/{payment_id}/allocations",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_payment_allocation(
    payment_id: uuid.UUID,
    payload: PaymentAllocationCreate,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PaymentResponse:
    payment = await owned_payment(session, payment_id, user.id, for_update=True)
    check_version(payment.version, payload.version)
    if payment.voided_at is not None:
        raise api_error(409, "PAYMENT_VOIDED", "已作废收款不能继续分摊")
    lesson = await owned_lesson(session, user, payload.lesson_id)
    if lesson.status == LessonStatus.RESCHEDULED:
        raise api_error(422, "INVALID_ALLOCATION_LESSON", "不能向已调课原记录分摊收款")
    existing = await session.scalar(
        select(PaymentAllocation).where(
            PaymentAllocation.payment_id == payment.id,
            PaymentAllocation.lesson_id == lesson.id,
        )
    )
    if existing is not None:
        raise api_error(409, "ALLOCATION_EXISTS", "该收款已经分摊到这节课程")
    allocated = int(
        await session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount_cents), 0)).where(
                PaymentAllocation.payment_id == payment.id
            )
        )
        or 0
    )
    if allocated + payload.amount_cents > payment.amount_cents:
        raise api_error(422, "ALLOCATION_EXCEEDS_PAYMENT", "分摊总额不能超过收款金额")
    session.add(
        PaymentAllocation(
            payment_id=payment.id,
            lesson_id=lesson.id,
            amount_cents=payload.amount_cents,
        )
    )
    payment.version += 1
    add_audit(
        session,
        request,
        user,
        "PAYMENT_ALLOCATION_CREATED",
        "Payment",
        payment.id,
        {"lesson_id": str(lesson.id), "amount_cents": payload.amount_cents},
    )
    await session.commit()
    return await payment_response(session, payment)


@router.post("/payments/{payment_id}/void", response_model=PaymentResponse)
async def void_payment(
    payment_id: uuid.UUID,
    payload: PaymentVoid,
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> PaymentResponse:
    payment = await owned_payment(session, payment_id, user.id, for_update=True)
    check_version(payment.version, payload.version)
    if payment.voided_at is not None:
        raise api_error(409, "PAYMENT_ALREADY_VOIDED", "收款已经作废")
    payment.voided_at = datetime.now(UTC)
    payment.void_reason = payload.reason.strip()
    payment.version += 1
    add_audit(
        session,
        request,
        user,
        "PAYMENT_VOIDED",
        "Payment",
        payment.id,
        {"reason": payload.reason, "amount_cents": payment.amount_cents},
    )
    await session.commit()
    return await payment_response(session, payment)


async def summary_response(
    session: AsyncSession,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> BillingSummaryResponse:
    rows = await billing_rows(session, user_id, start, end)
    active = [
        row
        for row in rows
        if row.response.lesson_status
        not in {LessonStatus.CANCELED.value, LessonStatus.RESCHEDULED.value}
    ]
    received = int(
        await session.scalar(
            select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
                Payment.owner_user_id == user_id,
                Payment.paid_at >= start,
                Payment.paid_at < end,
                Payment.voided_at.is_(None),
            )
        )
        or 0
    )
    grouped: dict[uuid.UUID, StudentBillingSummary] = {}
    for row in active:
        item = row.response
        current = grouped.get(row.student_id)
        if current is None:
            current = StudentBillingSummary(
                student_id=row.student_id,
                student_name=item.student_name,
                lesson_count=0,
                completed_minutes=0,
                receivable_cents=0,
                allocated_cents=0,
                outstanding_cents=0,
            )
            grouped[row.student_id] = current
        current.lesson_count += 1
        if item.lesson_status == LessonStatus.COMPLETED.value:
            current.completed_minutes += item.actual_minutes or 0
        current.receivable_cents += item.receivable_cents
        current.allocated_cents += item.allocated_cents
        current.outstanding_cents += item.outstanding_cents
    return BillingSummaryResponse(
        period_start=start,
        period_end=end,
        lesson_count=len(active),
        completed_minutes=sum(
            item.response.actual_minutes or 0
            for item in active
            if item.response.lesson_status == LessonStatus.COMPLETED.value
        ),
        receivable_cents=sum(item.response.receivable_cents for item in active),
        allocated_cents=sum(item.response.allocated_cents for item in active),
        outstanding_cents=sum(item.response.outstanding_cents for item in active),
        received_cents=received,
        students=sorted(grouped.values(), key=lambda item: item.student_name),
    )


@router.get("/billing/summary", response_model=BillingSummaryResponse)
async def get_billing_summary(
    user: UserDep,
    session: SessionDep,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> BillingSummaryResponse:
    start, end = resolve_period(date_from, date_to)
    return await summary_response(session, user.id, start, end)


def safe_sheet_text(value: str) -> str:
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_header(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename)}"


@router.get("/billing/export.csv")
async def export_billing_csv(
    user: UserDep,
    session: SessionDep,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
    start, end = resolve_period(date_from, date_to)
    rows = await billing_rows(session, user.id, start, end)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "日期",
            "学生",
            "学科",
            "主题",
            "课程状态",
            "计划分钟",
            "实际分钟",
            "单价(元/小时)",
            "应收(元)",
            "已分摊(元)",
            "未收(元)",
            "付款状态",
        ]
    )
    for row in rows:
        item = row.response
        writer.writerow(
            [
                item.scheduled_start.astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M"),
                safe_sheet_text(item.student_name),
                safe_sheet_text(item.subject_name),
                safe_sheet_text(item.theme),
                item.lesson_status,
                item.planned_minutes,
                item.actual_minutes or "",
                f"{Decimal(item.unit_price_cents) / 100:.2f}",
                f"{Decimal(item.receivable_cents) / 100:.2f}",
                f"{Decimal(item.allocated_cents) / 100:.2f}",
                f"{Decimal(item.outstanding_cents) / 100:.2f}",
                item.payment_status,
            ]
        )
    filename = f"课时收费_{start.astimezone(SHANGHAI):%Y%m%d}_{end.astimezone(SHANGHAI):%Y%m%d}.csv"
    return Response(
        content=stream.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": export_header(filename)},
    )


@router.get("/billing/export.xlsx")
async def export_billing_xlsx(
    user: UserDep,
    session: SessionDep,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
    start, end = resolve_period(date_from, date_to)
    rows = await billing_rows(session, user.id, start, end)
    workbook = Workbook()
    sheet = workbook.active
    if sheet is None:
        raise RuntimeError("Workbook did not create an active worksheet")
    sheet.title = "课时收费"
    headers = [
        "日期",
        "学生",
        "学科",
        "主题",
        "课程状态",
        "计划分钟",
        "实际分钟",
        "单价(元/小时)",
        "应收(元)",
        "已分摊(元)",
        "未收(元)",
        "付款状态",
    ]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for row in rows:
        item = row.response
        sheet.append(
            [
                item.scheduled_start.astimezone(SHANGHAI).replace(tzinfo=None),
                safe_sheet_text(item.student_name),
                safe_sheet_text(item.subject_name),
                safe_sheet_text(item.theme),
                item.lesson_status,
                item.planned_minutes,
                item.actual_minutes,
                item.unit_price_cents / 100,
                item.receivable_cents / 100,
                item.allocated_cents / 100,
                item.outstanding_cents / 100,
                item.payment_status,
            ]
        )
    for column in ("H", "I", "J", "K"):
        for cell in sheet[column][1:]:
            cell.number_format = '¥#,##0.00'
    for column, width in {
        "A": 20,
        "B": 16,
        "C": 14,
        "D": 28,
        "E": 14,
        "F": 12,
        "G": 12,
        "H": 18,
        "I": 14,
        "J": 14,
        "K": 14,
        "L": 14,
    }.items():
        sheet.column_dimensions[column].width = width
    output = io.BytesIO()
    workbook.save(output)
    filename = (
        f"课时收费_{start.astimezone(SHANGHAI):%Y%m%d}_"
        f"{end.astimezone(SHANGHAI):%Y%m%d}.xlsx"
    )
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": export_header(filename)},
    )
