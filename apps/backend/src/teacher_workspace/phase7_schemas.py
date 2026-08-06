from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MaterialPurpose = Literal[
    "TEACHING_MATERIAL",
    "EXAM_PAPER",
    "OLD_LESSON_PLAN",
    "OTHER_REFERENCE",
]


class MaterialResponse(BaseModel):
    id: uuid.UUID
    student_subject_id: uuid.UUID
    student_name: str
    subject_name: str
    purpose: MaterialPurpose
    display_name: str
    mime_type: str
    size_bytes: int
    processing_status: str
    chunk_count: int
    extracted_chars: int
    version: int
    created_at: datetime


class MaterialArchiveRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=500)
