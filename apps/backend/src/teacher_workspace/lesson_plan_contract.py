from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeBlock(ContractModel):
    minutes: int = Field(ge=1, le=720)
    title: str = Field(min_length=1, max_length=200)
    activities_markdown: str = Field(min_length=1, max_length=10000)


class TeachingSection(ContractModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    body_markdown: str = Field(min_length=1, max_length=30000)


class QuestionItem(ContractModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    stem_markdown: str = Field(min_length=1, max_length=20000)
    answer_markdown: str = Field(min_length=1, max_length=20000)
    analysis_markdown: str = Field(min_length=1, max_length=30000)
    difficulty: Literal["BASIC", "MEDIUM", "CHALLENGING"]


class LessonPlanContent(ContractModel):
    schema_version: Literal["1.0"]
    objectives: list[str] = Field(min_length=1, max_length=12)
    schedule: list[TimeBlock] = Field(min_length=1, max_length=24)
    knowledge_explanations: list[TeachingSection] = Field(min_length=1, max_length=30)
    examples: list[QuestionItem] = Field(max_length=30)
    in_class_exercises: list[QuestionItem] = Field(max_length=50)
    common_mistakes: list[str] = Field(max_length=30)
    homework: list[QuestionItem] = Field(max_length=50)
    teacher_notes: list[str] = Field(max_length=30)

    @model_validator(mode="after")
    def validate_structure(self) -> LessonPlanContent:
        if sum(block.minutes for block in self.schedule) > 720:
            raise ValueError("教案时间安排总时长不能超过 720 分钟")
        identifiers = [section.id for section in self.knowledge_explanations]
        identifiers.extend(item.id for item in self.examples)
        identifiers.extend(item.id for item in self.in_class_exercises)
        identifiers.extend(item.id for item in self.homework)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("教案区块和题目 ID 必须唯一")
        return self
