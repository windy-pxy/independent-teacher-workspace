from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from teacher_workspace.models import (
    MasteryLevel,
    QuestionSetVersionSource,
    ReviewStatus,
    WrongQuestionVersionSource,
)
from teacher_workspace.phase2_schemas import AIJobResponse
from teacher_workspace.phase4_contract import (
    Difficulty,
    GeneratedQuestionSetContent,
    WrongQuestionContent,
)


class WrongQuestionCreate(BaseModel):
    student_subject_id: uuid.UUID
    content: WrongQuestionContent
    mastery_status: MasteryLevel = MasteryLevel.WEAK


class WrongQuestionSave(BaseModel):
    content: WrongQuestionContent
    change_summary: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class ReviewAction(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class WrongQuestionReviewCreate(BaseModel):
    result_level: MasteryLevel
    notes: str = Field(min_length=1, max_length=5000)
    reviewed_at: datetime | None = None
    version: int = Field(ge=1)


class ArchiveWrongQuestion(BaseModel):
    confirmation: str = Field(pattern="^确认归档$")
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    mime_type: str
    size_bytes: int
    processing_status: str
    created_at: datetime


class WrongQuestionVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    source: WrongQuestionVersionSource
    status: ReviewStatus
    content: WrongQuestionContent
    image_material_id: uuid.UUID | None
    change_summary: str
    ai_job_id: uuid.UUID | None
    created_at: datetime


class WrongQuestionResponse(BaseModel):
    id: uuid.UUID
    student_subject_id: uuid.UUID
    student_name: str
    subject_name: str
    status: ReviewStatus
    current_version_number: int
    approved_version_number: int | None
    mastery_status: MasteryLevel
    last_reviewed_at: datetime | None
    review_count: int
    version: int
    current_version: WrongQuestionVersionResponse


class WrongQuestionReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wrong_question_id: uuid.UUID
    result_level: MasteryLevel
    notes: str
    reviewed_at: datetime


class RecognitionJobResponse(BaseModel):
    wrong_question: WrongQuestionResponse
    job: AIJobResponse


class GenerateQuestionSetRequest(BaseModel):
    student_subject_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    knowledge_point_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    wrong_question_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    target_difficulty: Difficulty = "MEDIUM"
    quantity: int = Field(default=5, ge=1, le=30)
    extra_requirements: str | None = Field(default=None, max_length=3000)


class QuestionSetSave(BaseModel):
    content: GeneratedQuestionSetContent
    change_summary: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class QuestionSetVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    source: QuestionSetVersionSource
    status: ReviewStatus
    content: GeneratedQuestionSetContent
    change_summary: str
    ai_job_id: uuid.UUID | None
    created_at: datetime


class QuestionSetResponse(BaseModel):
    id: uuid.UUID
    student_subject_id: uuid.UUID
    student_name: str
    subject_name: str
    title: str
    status: ReviewStatus
    current_version_number: int
    approved_version_number: int | None
    parameters: dict[str, object]
    version: int
    current_version: QuestionSetVersionResponse | None


class QuestionSetJobResponse(BaseModel):
    question_set: QuestionSetResponse
    job: AIJobResponse
