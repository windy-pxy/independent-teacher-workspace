from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teacher_workspace.models import MasteryLevel, PlanItemStatus


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanProgressProposal(ContractModel):
    plan_item_id: uuid.UUID
    status: Literal[
        PlanItemStatus.IN_PROGRESS,
        PlanItemStatus.COMPLETED,
        PlanItemStatus.REVIEW_NEEDED,
    ]
    actual_minutes_delta: int = Field(ge=0, le=720)
    progress_note: str = Field(min_length=1, max_length=2000)


class MasteryProposal(ContractModel):
    knowledge_point_id: uuid.UUID | None
    knowledge_point_name: str = Field(min_length=1, max_length=200)
    level: MasteryLevel
    evidence_note: str = Field(min_length=1, max_length=2000)


class LessonFeedbackContent(ContractModel):
    schema_version: Literal["1.0"]
    actual_completed_content: list[str] = Field(max_length=50)
    unfinished_content: list[str] = Field(max_length=50)
    student_performance: str = Field(min_length=1, max_length=5000)
    strong_knowledge_points: list[str] = Field(max_length=50)
    weak_knowledge_points: list[str] = Field(max_length=50)
    typical_mistakes: list[str] = Field(max_length=50)
    homework_completion: str = Field(min_length=1, max_length=3000)
    next_lesson_special_arrangement: str = Field(min_length=1, max_length=3000)
    structured_summary: str = Field(min_length=1, max_length=10000)
    next_lesson_suggestion: str = Field(min_length=1, max_length=10000)
    plan_progress_updates: list[PlanProgressProposal] = Field(max_length=100)
    mastery_updates: list[MasteryProposal] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_unique_targets(self) -> LessonFeedbackContent:
        plan_ids = [item.plan_item_id for item in self.plan_progress_updates]
        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("同一计划条目不能出现多次")
        mastery_keys = [
            str(item.knowledge_point_id)
            if item.knowledge_point_id is not None
            else " ".join(item.knowledge_point_name.lower().split())
            for item in self.mastery_updates
        ]
        if len(mastery_keys) != len(set(mastery_keys)):
            raise ValueError("同一知识点不能出现多次")
        return self
