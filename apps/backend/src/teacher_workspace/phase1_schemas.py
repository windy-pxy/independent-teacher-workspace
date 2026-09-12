from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from teacher_workspace.models import LessonStatus, LessonType, PlanItemStatus, PlanItemType

ShortText = Annotated[str, Field(min_length=1, max_length=100)]
Reason = Annotated[str, Field(min_length=2, max_length=500)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AuthUser(BaseModel):
    id: UUID
    username: str
    deletion_scheduled_for: datetime | None = None


class LoginResponse(BaseModel):
    user: AuthUser


class ArchiveRequest(BaseModel):
    version: int = Field(ge=1)
    reason: Reason


class StudentCreate(BaseModel):
    display_name: ShortText
    grade: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=200)
    learning_characteristics: str | None = Field(default=None, max_length=5000)
    guardian_requirements: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)


class StudentUpdate(StudentCreate):
    version: int = Field(ge=1)


class StudentResponse(StudentCreate):
    id: UUID
    version: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubjectCreate(BaseModel):
    name: ShortText
    description: str | None = Field(default=None, max_length=2000)


class SubjectUpdate(SubjectCreate):
    version: int = Field(ge=1)


class SubjectResponse(SubjectCreate):
    id: UUID
    version: int
    archived_at: datetime | None


class StudentSubjectCreate(BaseModel):
    student_id: UUID
    subject_id: UUID
    textbook_version: str | None = Field(default=None, max_length=200)
    current_foundation: str | None = Field(default=None, max_length=5000)
    overall_goal: str | None = Field(default=None, max_length=5000)
    stage_goal: str | None = Field(default=None, max_length=5000)
    teaching_requirements: str | None = Field(default=None, max_length=5000)
    attention_notes: str | None = Field(default=None, max_length=5000)


class StudentSubjectUpdate(BaseModel):
    textbook_version: str | None = Field(default=None, max_length=200)
    current_foundation: str | None = Field(default=None, max_length=5000)
    overall_goal: str | None = Field(default=None, max_length=5000)
    stage_goal: str | None = Field(default=None, max_length=5000)
    teaching_requirements: str | None = Field(default=None, max_length=5000)
    attention_notes: str | None = Field(default=None, max_length=5000)
    version: int = Field(ge=1)


class StudentSubjectResponse(StudentSubjectUpdate):
    id: UUID
    student_id: UUID
    student_name: str
    subject_id: UUID
    subject_name: str
    archived_at: datetime | None


class PlanCreate(BaseModel):
    student_subject_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class PlanUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    version: int = Field(ge=1)
    adjustment_reason: Reason


class PlanItemCreate(BaseModel):
    parent_id: UUID | None = None
    item_type: PlanItemType
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    sort_order: int = Field(default=0, ge=0, le=100000)
    estimated_minutes: int = Field(default=0, ge=0, le=100000)
    adjustment_reason: Reason


class PlanItemUpdate(BaseModel):
    parent_id: UUID | None = None
    item_type: PlanItemType
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    sort_order: int = Field(default=0, ge=0, le=100000)
    estimated_minutes: int = Field(default=0, ge=0, le=100000)
    actual_minutes: int = Field(default=0, ge=0, le=100000)
    status: PlanItemStatus
    progress_notes: str | None = Field(default=None, max_length=5000)
    version: int = Field(ge=1)
    adjustment_reason: Reason


class PlanItemResponse(BaseModel):
    id: UUID
    plan_id: UUID
    parent_id: UUID | None
    item_type: PlanItemType
    title: str
    description: str | None
    sort_order: int
    estimated_minutes: int
    actual_minutes: int
    status: PlanItemStatus
    progress_notes: str | None
    version: int


class PlanResponse(BaseModel):
    id: UUID
    student_subject_id: UUID
    student_name: str
    subject_name: str
    name: str
    description: str | None
    version: int
    archived_at: datetime | None
    items: list[PlanItemResponse] = Field(default_factory=list)


class PlanRevisionResponse(BaseModel):
    version_number: int
    adjustment_reason: str
    created_at: datetime


class LessonCreate(BaseModel):
    student_subject_id: UUID
    scheduled_start: datetime
    planned_minutes: int = Field(ge=15, le=720)
    unit_price_cents: int = Field(default=0, ge=0, le=100_000_000)
    lesson_type: LessonType
    theme: str = Field(min_length=1, max_length=300)
    special_requirements: str | None = Field(default=None, max_length=5000)
    plan_item_ids: list[UUID] = Field(default_factory=list, max_length=100)
    makeup_for_lesson_id: UUID | None = None

    @model_validator(mode="after")
    def require_timezone(self) -> "LessonCreate":
        if self.scheduled_start.tzinfo is None:
            raise ValueError("scheduled_start must include a timezone")
        return self


class LessonUpdate(BaseModel):
    scheduled_start: datetime
    planned_minutes: int = Field(ge=15, le=720)
    unit_price_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    lesson_type: LessonType
    theme: str = Field(min_length=1, max_length=300)
    special_requirements: str | None = Field(default=None, max_length=5000)
    plan_item_ids: list[UUID] = Field(default_factory=list, max_length=100)
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def require_timezone(self) -> "LessonUpdate":
        if self.scheduled_start.tzinfo is None:
            raise ValueError("scheduled_start must include a timezone")
        return self


class ProgressConfirmation(BaseModel):
    plan_item_id: UUID
    status: PlanItemStatus
    actual_minutes_delta: int = Field(default=0, ge=0, le=720)
    progress_notes: str | None = Field(default=None, max_length=2000)


class LessonComplete(BaseModel):
    actual_minutes: int = Field(ge=1, le=720)
    progress_updates: list[ProgressConfirmation] = Field(default_factory=list, max_length=100)
    adjustment_reason: Reason = "课程完成时确认教学进度"


class LessonCancel(BaseModel):
    reason: Reason
    version: int = Field(ge=1)


class LessonReschedule(BaseModel):
    scheduled_start: datetime
    planned_minutes: int | None = Field(default=None, ge=15, le=720)
    reason: Reason
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def require_timezone(self) -> "LessonReschedule":
        if self.scheduled_start.tzinfo is None:
            raise ValueError("scheduled_start must include a timezone")
        return self


class LessonResponse(BaseModel):
    id: UUID
    student_subject_id: UUID
    student_name: str
    subject_name: str
    scheduled_start: datetime
    planned_minutes: int
    actual_minutes: int | None
    unit_price_cents: int
    receivable_cents: int
    receivable_is_overridden: bool
    lesson_type: LessonType
    theme: str
    special_requirements: str | None
    status: LessonStatus
    rescheduled_from_lesson_id: UUID | None
    makeup_for_lesson_id: UUID | None
    cancellation_reason: str | None
    plan_item_ids: list[UUID]
    version: int


class DashboardProgress(BaseModel):
    student_subject_id: UUID
    student_name: str
    subject_name: str
    completed_items: int
    total_items: int
    percent: int


class DashboardResponse(BaseModel):
    today: list[LessonResponse]
    next_seven_days: list[LessonResponse]
    progress: list[DashboardProgress]
    planned_this_week: int
    completed_this_month: int
    pending_feedback_count: int
    month_receivable_cents: int
    month_received_cents: int
    month_outstanding_cents: int
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
