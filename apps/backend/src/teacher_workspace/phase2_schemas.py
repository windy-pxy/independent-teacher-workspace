from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from teacher_workspace.lesson_plan_contract import LessonPlanContent
from teacher_workspace.models import (
    AIJobStatus,
    DocumentVersionSource,
    ReviewStatus,
)


class PromptTemplateCreate(BaseModel):
    template_key: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=100)
    grade_band: str | None = Field(default=None, max_length=50)
    subject_id: uuid.UUID | None = None
    system_prompt: str = Field(min_length=20, max_length=30000)
    user_prompt_template: str = Field(min_length=20, max_length=30000)
    change_reason: str = Field(min_length=2, max_length=500)


class PromptTemplateUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=20, max_length=30000)
    user_prompt_template: str = Field(min_length=20, max_length=30000)
    change_reason: str = Field(min_length=2, max_length=500)
    current_version_number: int = Field(ge=1)


class PromptTemplateVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    system_prompt: str
    user_prompt_template: str
    output_schema: dict[str, object]
    change_reason: str
    created_at: datetime


class PromptTemplateResponse(BaseModel):
    id: uuid.UUID
    template_key: str
    name: str
    purpose: str
    grade_band: str | None
    subject_id: uuid.UUID | None
    current_version_number: int
    current_version: PromptTemplateVersionResponse


class GenerateLessonPlanRequest(BaseModel):
    template_id: uuid.UUID | None = None
    extra_requirements: str | None = Field(default=None, max_length=5000)


class RegenerateSectionRequest(BaseModel):
    section: Literal[
        "objectives",
        "schedule",
        "knowledge_explanations",
        "examples",
        "in_class_exercises",
        "common_mistakes",
        "homework",
        "teacher_notes",
    ]
    instructions: str = Field(min_length=2, max_length=3000)
    version: int = Field(ge=1)


class SaveDocumentRequest(BaseModel):
    content: LessonPlanContent
    change_summary: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class ReviewActionRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    version: int = Field(ge=1)


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    source: DocumentVersionSource
    status: ReviewStatus
    content: LessonPlanContent
    change_summary: str
    ai_job_id: uuid.UUID | None
    docx_object_key: str | None
    created_at: datetime


class LessonDocumentResponse(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    status: ReviewStatus
    current_version_number: int
    approved_version_number: int | None
    version: int
    current_version: DocumentVersionResponse


class AIJobResponse(BaseModel):
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


class AISettingsResponse(BaseModel):
    provider: str
    model: str | None
    real_provider_configured: bool
    development_default_is_mock: bool = True
