from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PaymentStatus = Literal["UNPAID", "PARTIAL", "PAID", "OVERPAID"]


class LessonPricingUpdate(BaseModel):
    unit_price_cents: int = Field(ge=0, le=100_000_000)
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class LessonReceivableOverride(BaseModel):
    receivable_cents: int = Field(ge=0, le=10_000_000_000)
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class LessonReceivableReset(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class PaymentAllocationInput(BaseModel):
    lesson_id: uuid.UUID
    amount_cents: int = Field(gt=0, le=10_000_000_000)


class PaymentCreate(BaseModel):
    amount_cents: int = Field(gt=0, le=10_000_000_000)
    paid_at: datetime
    method: str = Field(min_length=1, max_length=50)
    reference: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    allocations: list[PaymentAllocationInput] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_payment(self) -> PaymentCreate:
        if self.paid_at.tzinfo is None:
            raise ValueError("paid_at must include a timezone")
        lesson_ids = [item.lesson_id for item in self.allocations]
        if len(lesson_ids) != len(set(lesson_ids)):
            raise ValueError("同一笔收款不能重复分摊到同一课程")
        if sum(item.amount_cents for item in self.allocations) > self.amount_cents:
            raise ValueError("分摊总额不能超过收款金额")
        return self


class PaymentAllocationCreate(PaymentAllocationInput):
    version: int = Field(ge=1)


class PaymentVoid(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class PaymentAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lesson_id: uuid.UUID
    amount_cents: int
    created_at: datetime


class PaymentResponse(BaseModel):
    id: uuid.UUID
    amount_cents: int
    currency: Literal["CNY"] = "CNY"
    paid_at: datetime
    method: str
    reference: str | None
    notes: str | None
    voided_at: datetime | None
    void_reason: str | None
    allocated_cents: int
    unallocated_cents: int
    allocations: list[PaymentAllocationResponse]
    version: int
    created_at: datetime


class LessonBillingResponse(BaseModel):
    lesson_id: uuid.UUID
    student_subject_id: uuid.UUID
    student_name: str
    subject_name: str
    scheduled_start: datetime
    lesson_status: str
    theme: str
    planned_minutes: int
    actual_minutes: int | None
    unit_price_cents: int
    receivable_cents: int
    receivable_is_overridden: bool
    receivable_override_reason: str | None
    allocated_cents: int
    outstanding_cents: int
    payment_status: PaymentStatus
    version: int


class StudentBillingSummary(BaseModel):
    student_id: uuid.UUID
    student_name: str
    lesson_count: int
    completed_minutes: int
    receivable_cents: int
    allocated_cents: int
    outstanding_cents: int


class BillingSummaryResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    currency: Literal["CNY"] = "CNY"
    lesson_count: int
    completed_minutes: int
    receivable_cents: int
    allocated_cents: int
    outstanding_cents: int
    received_cents: int
    students: list[StudentBillingSummary]
