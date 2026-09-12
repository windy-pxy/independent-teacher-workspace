from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AIJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class PlanItemType(StrEnum):
    CHAPTER = "CHAPTER"
    KNOWLEDGE_POINT = "KNOWLEDGE_POINT"
    TOPIC = "TOPIC"


class PlanItemStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class LessonType(StrEnum):
    NEW_LESSON = "NEW_LESSON"
    REVIEW = "REVIEW"
    EXERCISE = "EXERCISE"
    EXAM = "EXAM"
    PAPER_REVIEW = "PAPER_REVIEW"


class LessonStatus(StrEnum):
    PLANNED = "PLANNED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    RESCHEDULED = "RESCHEDULED"


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class DocumentVersionSource(StrEnum):
    AI_GENERATED = "AI_GENERATED"
    MANUAL_EDIT = "MANUAL_EDIT"
    PARTIAL_REGENERATION = "PARTIAL_REGENERATION"


class FeedbackVersionSource(StrEnum):
    QUICK_ENTRY = "QUICK_ENTRY"
    AI_ORGANIZED = "AI_ORGANIZED"
    MANUAL_EDIT = "MANUAL_EDIT"


class MasteryLevel(StrEnum):
    UNLEARNED = "UNLEARNED"
    WEAK = "WEAK"
    DEVELOPING = "DEVELOPING"
    PROFICIENT = "PROFICIENT"
    MASTERED = "MASTERED"


class WrongQuestionVersionSource(StrEnum):
    MANUAL_ENTRY = "MANUAL_ENTRY"
    AI_RECOGNIZED = "AI_RECOGNIZED"
    MANUAL_EDIT = "MANUAL_EDIT"


class QuestionSetVersionSource(StrEnum):
    AI_GENERATED = "AI_GENERATED"
    MANUAL_EDIT = "MANUAL_EDIT"


class RegistrationInvite(Base):
    __tablename__ = "registration_invites"
    __table_args__ = (
        CheckConstraint("max_uses > 0", name="ck_registration_invites_max_uses_positive"),
        CheckConstraint(
            "uses_count >= 0 AND uses_count <= max_uses",
            name="ck_registration_invites_uses_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(100))
    max_uses: Mapped[int] = mapped_column(Integer)
    uses_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "ai_monthly_job_limit >= 0",
            name="ck_users_ai_monthly_job_limit_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    recovery_code_hash: Mapped[str | None] = mapped_column(String(64))
    registration_invite_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("registration_invites.id", ondelete="SET NULL"), index=True
    )
    privacy_notice_version: Mapped[str | None] = mapped_column(String(20))
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_access_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ai_monthly_job_limit: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger)
    attempts: Mapped[int] = mapped_column(Integer)


class AIUsageMonth(Base):
    __tablename__ = "ai_usage_months"
    __table_args__ = (
        CheckConstraint("job_count >= 0", name="ck_ai_usage_job_count_nonnegative"),
        CheckConstraint("input_tokens >= 0", name="ck_ai_usage_input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="ck_ai_usage_output_tokens_nonnegative"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    month_key: Mapped[str] = mapped_column(String(7), primary_key=True)
    job_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class AIJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (Index("ix_ai_jobs_claim", "status", "available_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    prompt_template_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_template_versions.id", ondelete="SET NULL")
    )
    task_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[AIJobStatus] = mapped_column(
        Enum(AIJobStatus, native_enum=False, length=20),
        default=AIJobStatus.QUEUED,
    )
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    model: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leased_by: Mapped[str | None] = mapped_column(String(100))
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    attempts: Mapped[list[AIJobAttempt]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class AIJobAttempt(Base):
    __tablename__ = "ai_job_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_jobs.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)

    job: Mapped[AIJob] = relationship(back_populates="attempts")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    change_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("owner_user_id", "normalized_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (Index("ix_students_owner_archived", "owner_user_id", "archived_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(100))
    grade: Mapped[str | None] = mapped_column(String(50))
    region: Mapped[str | None] = mapped_column(String(100))
    school: Mapped[str | None] = mapped_column(String(200))
    learning_characteristics: Mapped[str | None] = mapped_column(Text)
    guardian_requirements: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class StudentSubject(Base):
    __tablename__ = "student_subjects"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id"),
        Index("ix_student_subjects_student", "student_id", "archived_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), index=True
    )
    textbook_version: Mapped[str | None] = mapped_column(String(200))
    current_foundation: Mapped[str | None] = mapped_column(Text)
    overall_goal: Mapped[str | None] = mapped_column(Text)
    stage_goal: Mapped[str | None] = mapped_column(Text)
    teaching_requirements: Mapped[str | None] = mapped_column(Text)
    attention_notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    student: Mapped[Student] = relationship()
    subject: Mapped[Subject] = relationship()


class TeachingPlan(Base):
    __tablename__ = "teaching_plans"
    __table_args__ = (
        Index("ix_teaching_plans_student_subject", "student_subject_id", "archived_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    student_subject: Mapped[StudentSubject] = relationship()


class TeachingPlanItem(Base):
    __tablename__ = "teaching_plan_items"
    __table_args__ = (Index("ix_plan_items_tree", "plan_id", "parent_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teaching_plans.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teaching_plan_items.id", ondelete="CASCADE")
    )
    item_type: Mapped[PlanItemType] = mapped_column(
        Enum(PlanItemType, native_enum=False, length=30)
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0)
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[PlanItemStatus] = mapped_column(
        Enum(PlanItemStatus, native_enum=False, length=30),
        default=PlanItemStatus.NOT_STARTED,
    )
    progress_notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TeachingPlanRevision(Base):
    __tablename__ = "teaching_plan_revisions"
    __table_args__ = (UniqueConstraint("plan_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teaching_plans.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    adjustment_reason: Mapped[str] = mapped_column(String(500))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        Index("ix_lessons_student_subject_start", "student_subject_id", "scheduled_start"),
        Index("ix_lessons_status_start", "status", "scheduled_start"),
        CheckConstraint("unit_price_cents >= 0", name="ck_lessons_unit_price_nonnegative"),
        CheckConstraint("receivable_cents >= 0", name="ck_lessons_receivable_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="RESTRICT"), index=True
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_minutes: Mapped[int] = mapped_column(Integer)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    receivable_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    receivable_is_overridden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    receivable_override_reason: Mapped[str | None] = mapped_column(String(500))
    lesson_type: Mapped[LessonType] = mapped_column(Enum(LessonType, native_enum=False, length=30))
    theme: Mapped[str] = mapped_column(String(300))
    special_requirements: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LessonStatus] = mapped_column(
        Enum(LessonStatus, native_enum=False, length=20), default=LessonStatus.PLANNED
    )
    rescheduled_from_lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="SET NULL")
    )
    makeup_for_lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="SET NULL")
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    student_subject: Mapped[StudentSubject] = relationship()


class LessonPlanItem(Base):
    __tablename__ = "lesson_plan_items"
    __table_args__ = (UniqueConstraint("lesson_id", "plan_item_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True
    )
    plan_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teaching_plan_items.id", ondelete="RESTRICT"), index=True
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_payments_amount_positive"),
        Index("ix_payments_owner_paid_at", "owner_user_id", "paid_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", server_default="CNY")
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    method: Mapped[str] = mapped_column(String(50))
    reference: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    void_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint("payment_id", "lesson_id"),
        CheckConstraint("amount_cents > 0", name="ck_payment_allocations_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="RESTRICT"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "template_key", "grade_band", "subject_id"),
        Index("ix_prompt_templates_owner_key", "owner_user_id", "template_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    template_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(100))
    grade_band: Mapped[str | None] = mapped_column(String(50))
    current_version_number: Mapped[int] = mapped_column(Integer, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PromptTemplateVersion(Base):
    __tablename__ = "prompt_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    system_prompt: Mapped[str] = mapped_column(Text)
    user_prompt_template: Mapped[str] = mapped_column(Text)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_reason: Mapped[str] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LessonDocument(Base):
    __tablename__ = "lesson_documents"
    __table_args__ = (
        UniqueConstraint("lesson_id", "document_type"),
        Index("ix_lesson_documents_lesson_status", "lesson_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(50), default="LESSON_PLAN")
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=1)
    approved_version_number: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lesson_documents.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[DocumentVersionSource] = mapped_column(
        Enum(DocumentVersionSource, native_enum=False, length=30)
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(500))
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_jobs.id", ondelete="SET NULL"), unique=True
    )
    docx_object_key: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LessonFeedback(Base):
    __tablename__ = "lesson_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=0)
    approved_version_number: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LessonFeedbackVersion(Base):
    __tablename__ = "lesson_feedback_versions"
    __table_args__ = (UniqueConstraint("feedback_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lesson_feedbacks.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[FeedbackVersionSource] = mapped_column(
        Enum(FeedbackVersionSource, native_enum=False, length=30)
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    raw_input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(500))
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_jobs.id", ondelete="SET NULL"), unique=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint("subject_id", "normalized_name"),
        Index("ix_knowledge_points_subject_parent", "subject_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StudentMastery(Base):
    __tablename__ = "student_masteries"
    __table_args__ = (
        UniqueConstraint("student_subject_id", "knowledge_point_id"),
        Index("ix_student_masteries_level", "student_subject_id", "level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), index=True
    )
    level: Mapped[MasteryLevel] = mapped_column(
        Enum(MasteryLevel, native_enum=False, length=30),
        default=MasteryLevel.UNLEARNED,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MasteryEvidence(Base):
    __tablename__ = "mastery_evidence"
    __table_args__ = (
        UniqueConstraint("mastery_id", "feedback_version_id"),
        Index("ix_mastery_evidence_mastery_created", "mastery_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    mastery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_masteries.id", ondelete="CASCADE"), index=True
    )
    feedback_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lesson_feedback_versions.id", ondelete="RESTRICT"), index=True
    )
    previous_level: Mapped[MasteryLevel] = mapped_column(
        Enum(MasteryLevel, native_enum=False, length=30)
    )
    new_level: Mapped[MasteryLevel] = mapped_column(
        Enum(MasteryLevel, native_enum=False, length=30)
    )
    reason: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UploadedMaterial(Base):
    __tablename__ = "uploaded_materials"
    __table_args__ = (Index("ix_uploaded_materials_owner_sha", "owner_user_id", "sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    student_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    processing_status: Mapped[str] = mapped_column(String(30), default="READY")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MaterialChunk(Base):
    __tablename__ = "material_chunks"
    __table_args__ = (
        UniqueConstraint("material_id", "chunk_index"),
        Index("ix_material_chunks_material_order", "material_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0", name="ck_material_chunks_index_nonnegative"),
        CheckConstraint("char_count > 0", name="ck_material_chunks_chars_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploaded_materials.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    source_locator: Mapped[str | None] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"
    __table_args__ = (
        Index(
            "ix_wrong_questions_subject_mastery_review",
            "student_subject_id",
            "mastery_status",
            "last_reviewed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=1)
    approved_version_number: Mapped[int | None] = mapped_column(Integer)
    mastery_status: Mapped[MasteryLevel] = mapped_column(
        Enum(MasteryLevel, native_enum=False, length=30), default=MasteryLevel.WEAK
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class WrongQuestionVersion(Base):
    __tablename__ = "wrong_question_versions"
    __table_args__ = (UniqueConstraint("wrong_question_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    wrong_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wrong_questions.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[WrongQuestionVersionSource] = mapped_column(
        Enum(WrongQuestionVersionSource, native_enum=False, length=30)
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    image_material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("uploaded_materials.id", ondelete="SET NULL"), index=True
    )
    change_summary: Mapped[str] = mapped_column(String(500))
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_jobs.id", ondelete="SET NULL"), unique=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WrongQuestionKnowledgePoint(Base):
    __tablename__ = "wrong_question_knowledge_points"
    __table_args__ = (UniqueConstraint("wrong_question_id", "knowledge_point_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    wrong_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wrong_questions.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), index=True
    )


class WrongQuestionReview(Base):
    __tablename__ = "wrong_question_reviews"
    __table_args__ = (
        Index(
            "ix_wrong_question_reviews_question_time",
            "wrong_question_id",
            "reviewed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    wrong_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wrong_questions.id", ondelete="CASCADE"), index=True
    )
    result_level: Mapped[MasteryLevel] = mapped_column(
        Enum(MasteryLevel, native_enum=False, length=30)
    )
    notes: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class GeneratedQuestionSet(Base):
    __tablename__ = "generated_question_sets"
    __table_args__ = (
        Index("ix_generated_question_sets_subject_status", "student_subject_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_subjects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=0)
    approved_version_number: Mapped[int | None] = mapped_column(Integer)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class GeneratedQuestionSetVersion(Base):
    __tablename__ = "generated_question_set_versions"
    __table_args__ = (UniqueConstraint("question_set_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_question_sets.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[QuestionSetVersionSource] = mapped_column(
        Enum(QuestionSetVersionSource, native_enum=False, length=30)
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=30), default=ReviewStatus.DRAFT
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(500))
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_jobs.id", ondelete="SET NULL"), unique=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GeneratedQuestion(Base):
    __tablename__ = "generated_questions"
    __table_args__ = (
        UniqueConstraint("question_set_id", "approved_version_number", "question_key"),
        Index("ix_generated_questions_set_order", "question_set_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_question_sets.id", ondelete="CASCADE"), index=True
    )
    approved_version_number: Mapped[int] = mapped_column(Integer)
    question_key: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer)
    stem_markdown: Mapped[str] = mapped_column(Text)
    answer_markdown: Mapped[str] = mapped_column(Text)
    analysis_markdown: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GeneratedQuestionKnowledgePoint(Base):
    __tablename__ = "generated_question_knowledge_points"
    __table_args__ = (UniqueConstraint("generated_question_id", "knowledge_point_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generated_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_questions.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), index=True
    )
