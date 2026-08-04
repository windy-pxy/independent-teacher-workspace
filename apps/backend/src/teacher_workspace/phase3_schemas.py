from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teacher_workspace.feedback_contract import LessonFeedbackContent
from teacher_workspace.models import (
    AIJobStatus,
    FeedbackVersionSource,
    MasteryLevel,
    ReviewStatus,
)


class QuickFeedbackInput(BaseModel):
    actual_completed_content: str | None = Field(default=None, max_length=5000)
    unfinished_content: str | None = Field(default=None, max_length=5000)
    student_performance: str | None = Field(default=None, max_length=5000)
    strong_knowledge_points: str | None = Field(default=None, max_length=5000)
    weak_knowledge_points: str | None = Field(default=None, max_length=5000)
    typical_mistakes: str | None = Field(default=None, max_length=5000)
    homework_completion: str | None = Field(default=None, max_length=3000)
    next_lesson_special_arrangement: str | None = Field(default=None, max_length=3000)

    @model_validator(mode="after")
    def require_some_input(self) -> QuickFeedbackInput:
        if not any(value and value.strip() for value in self.model_dump().values()):
            raise ValueError("至少填写一项课后关键词")
        return self


class FeedbackSaveRequest(BaseModel):
    content: LessonFeedbackContent
    change_summary: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class FeedbackReviewRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class FeedbackOrganizeRequest(BaseModel):
    instructions: str | None = Field(default=None, max_length=3000)
    version: int = Field(ge=1)


class FeedbackVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    source: FeedbackVersionSource
    status: ReviewStatus
    raw_input: dict[str, str | None]
    content: LessonFeedbackContent
    change_summary: str
    ai_job_id: uuid.UUID | None
    created_at: datetime


class LessonFeedbackResponse(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    status: ReviewStatus
    current_version_number: int
    approved_version_number: int | None
    version: int
    current_version: FeedbackVersionResponse


class FeedbackAIJobResponse(BaseModel):
    id: uuid.UUID
    task_type: str
    status: AIJobStatus
    provider: str
    model: str | None
    attempts_count: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class MasteryResponse(BaseModel):
    id: uuid.UUID
    student_subject_id: uuid.UUID
    knowledge_point_id: uuid.UUID
    knowledge_point_name: str
    level: MasteryLevel
    version: int
    updated_at: datetime
    evidence_count: int
