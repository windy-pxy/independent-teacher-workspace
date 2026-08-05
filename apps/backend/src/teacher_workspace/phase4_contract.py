from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Difficulty = Literal["BASIC", "MEDIUM", "ADVANCED"]


class KnowledgePointRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_point_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)


class WrongQuestionContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    question_text: str = Field(min_length=1, max_length=30000)
    source: str = Field(default="未记录", max_length=500)
    difficulty: Difficulty = "MEDIUM"
    student_answer: str = Field(default="", max_length=20000)
    correct_answer: str = Field(default="", max_length=20000)
    error_reason: str = Field(default="", max_length=5000)
    analysis: str = Field(default="", max_length=30000)
    knowledge_points: list[KnowledgePointRef] = Field(default_factory=list, max_length=20)
    recognition_notes: str = Field(default="", max_length=3000)

    @model_validator(mode="after")
    def unique_knowledge_points(self) -> WrongQuestionContent:
        ids = [item.knowledge_point_id for item in self.knowledge_points if item.knowledge_point_id]
        names = [" ".join(item.name.lower().split()) for item in self.knowledge_points]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("知识点不能重复")
        return self

    def validate_for_approval(self) -> None:
        required = {
            "正确答案": self.correct_answer,
            "错误原因": self.error_reason,
            "解析": self.analysis,
        }
        missing = [label for label, value in required.items() if not value.strip()]
        if missing:
            raise ValueError("批准前必须填写：" + "、".join(missing))


class GeneratedQuestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    stem_markdown: str = Field(min_length=1, max_length=30000)
    answer_markdown: str = Field(min_length=1, max_length=20000)
    analysis_markdown: str = Field(min_length=1, max_length=30000)
    difficulty: Difficulty
    knowledge_points: list[KnowledgePointRef] = Field(min_length=1, max_length=20)


class GeneratedQuestionSetContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(min_length=1, max_length=300)
    teacher_notes: str = Field(default="", max_length=5000)
    questions: list[GeneratedQuestionItem] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_question_keys(self) -> GeneratedQuestionSetContent:
        keys = [item.question_key for item in self.questions]
        if len(keys) != len(set(keys)):
            raise ValueError("题目键不能重复")
        return self


def wrong_question_json_schema() -> dict[str, object]:
    return WrongQuestionContent.model_json_schema()


def question_set_json_schema() -> dict[str, object]:
    return GeneratedQuestionSetContent.model_json_schema()
