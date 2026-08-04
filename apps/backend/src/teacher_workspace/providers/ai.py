from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI

from teacher_workspace.config import Settings


@dataclass(frozen=True)
class AICapabilities:
    text: bool
    structured_output: bool
    vision: bool
    cancellation: bool


@dataclass(frozen=True)
class AIRequest:
    prompt: str
    instructions: str | None = None
    schema: dict[str, Any] | None = None
    image_keys: tuple[str, ...] = ()
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class AIResult:
    content: str
    structured: dict[str, Any] | None = None
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(Protocol):
    @property
    def capabilities(self) -> AICapabilities: ...

    async def generate(self, request: AIRequest) -> AIResult: ...

    async def cancel(self, provider_request_id: str) -> bool: ...


class MockAIProvider:
    @property
    def capabilities(self) -> AICapabilities:
        return AICapabilities(text=True, structured_output=True, vision=True, cancellation=True)

    async def generate(self, request: AIRequest) -> AIResult:
        structured = None
        if request.schema:
            total_minutes = int((request.context or {}).get("planned_minutes", 120))
            weights = (10, 30, 35, 15, 10)
            durations = [max(1, total_minutes * weight // 100) for weight in weights]
            durations[-1] += total_minutes - sum(durations)
            structured = {
                "schema_version": "1.0",
                "objectives": ["理解本节核心概念", "能够独立完成基础与迁移练习"],
                "schedule": [
                    {
                        "minutes": durations[0],
                        "title": "复习与诊断",
                        "activities_markdown": "回顾前置知识，并用两个口头问题确认起点。",
                    },
                    {
                        "minutes": durations[1],
                        "title": "核心讲解",
                        "activities_markdown": "结合定义、步骤和反例讲解本节主题。",
                    },
                    {
                        "minutes": durations[2],
                        "title": "例题与练习",
                        "activities_markdown": "先示范，再由学生独立完成同类题。",
                    },
                    {
                        "minutes": durations[3],
                        "title": "纠错与提升",
                        "activities_markdown": "订正错误，归纳检查方法。",
                    },
                    {
                        "minutes": durations[4],
                        "title": "总结与作业",
                        "activities_markdown": "学生复述要点，布置分层作业。",
                    },
                ],
                "knowledge_explanations": [
                    {
                        "id": "core-concept",
                        "title": "核心知识讲解",
                        "body_markdown": "从**概念、步骤、检验**三个层次展开，并联系学生已有基础。",
                    }
                ],
                "examples": [
                    {
                        "id": "example-1",
                        "stem_markdown": "完成一道与本节主题直接相关的示例题。",
                        "answer_markdown": "按规范步骤得到正确结论。",
                        "analysis_markdown": "明确条件，选择方法，逐步计算并回代检查。",
                        "difficulty": "BASIC",
                    }
                ],
                "in_class_exercises": [
                    {
                        "id": "practice-1",
                        "stem_markdown": "独立完成一道同类变式题。",
                        "answer_markdown": "答案见解析步骤。",
                        "analysis_markdown": "先判断题型，再使用例题中的检查流程。",
                        "difficulty": "MEDIUM",
                    }
                ],
                "common_mistakes": ["忽略题目条件", "完成计算后没有检查"],
                "homework": [
                    {
                        "id": "homework-1",
                        "stem_markdown": "完成一道基础巩固题并写出完整过程。",
                        "answer_markdown": "答案随教师版教案提供。",
                        "analysis_markdown": "参照课堂步骤独立完成并检查。",
                        "difficulty": "BASIC",
                    }
                ],
                "teacher_notes": ["这是 Mock 生成的虚构草稿，必须由教师审核后使用。"],
            }
        return AIResult(
            content=(
                json.dumps(structured, ensure_ascii=False)
                if structured
                else "Mock AI response"
            ),
            structured=structured,
            provider_request_id="mock",
            input_tokens=0,
            output_tokens=0,
        )

    async def cancel(self, provider_request_id: str) -> bool:
        return provider_request_id == "mock"


class OpenAIResponsesProvider:
    def __init__(self, api_key: str, model: str, max_output_tokens: int) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens

    @property
    def capabilities(self) -> AICapabilities:
        return AICapabilities(
            text=True, structured_output=True, vision=True, cancellation=False
        )

    async def generate(self, request: AIRequest) -> AIResult:
        text_config: dict[str, object] | None = None
        if request.schema:
            text_config = {
                "format": {
                    "type": "json_schema",
                    "name": "teacher_workspace_output",
                    "schema": request.schema,
                    "strict": True,
                }
            }
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": request.instructions,
            "input": request.prompt,
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        if text_config is not None:
            request_kwargs["text"] = text_config
        response = await self.client.responses.create(**request_kwargs)
        structured = json.loads(response.output_text) if request.schema else None
        usage = response.usage
        return AIResult(
            content=response.output_text,
            structured=structured,
            provider_request_id=response.id,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )

    async def cancel(self, provider_request_id: str) -> bool:
        del provider_request_id
        return False


def create_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "mock":
        return MockAIProvider()
    if settings.ai_provider == "openai":
        if not settings.openai_api_key or not settings.openai_model:
            raise RuntimeError("OpenAI provider requires OPENAI_API_KEY and OPENAI_MODEL")
        return OpenAIResponsesProvider(
            settings.openai_api_key,
            settings.openai_model,
            settings.ai_max_output_tokens,
        )
    raise RuntimeError(f"Unsupported AI provider: {settings.ai_provider}")
