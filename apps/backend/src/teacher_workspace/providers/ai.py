from __future__ import annotations

import base64
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
    images: tuple[AIImageInput, ...] = ()
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class AIImageInput:
    mime_type: str
    content: bytes
    detail: str = "auto"


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
            context = request.context or {}
            if context.get("task_type") == "lesson_feedback":
                plan_item_ids = list(context.get("plan_item_ids") or [])
                structured = {
                    "schema_version": "1.0",
                    "actual_completed_content": ["完成本节计划的核心内容"],
                    "unfinished_content": ["未记录"],
                    "student_performance": "学生能跟随讲解完成基础练习，具体表现请教师复核。",
                    "strong_knowledge_points": ["基础概念识别"],
                    "weak_knowledge_points": ["综合应用"],
                    "typical_mistakes": ["步骤不完整"],
                    "homework_completion": "未记录",
                    "next_lesson_special_arrangement": "先进行五分钟诊断复习。",
                    "structured_summary": "本节完成核心内容，基础理解尚可，综合应用需要继续巩固。",
                    "next_lesson_suggestion": "复习薄弱知识点后安排一道基础题和一道变式题。",
                    "plan_progress_updates": (
                        [
                            {
                                "plan_item_id": plan_item_ids[0],
                                "status": "IN_PROGRESS",
                                "actual_minutes_delta": int(context.get("actual_minutes") or 0),
                                "progress_note": "根据课后反馈建议标记为进行中。",
                            }
                        ]
                        if plan_item_ids
                        else []
                    ),
                    "mastery_updates": [
                        {
                            "knowledge_point_id": None,
                            "knowledge_point_name": "综合应用",
                            "level": "WEAK",
                            "evidence_note": "课堂关键词显示综合应用仍需巩固。",
                        }
                    ],
                }
            elif context.get("task_type") == "wrong_question_recognition":
                structured = {
                    "schema_version": "1.0",
                    "question_text": "【Mock 图片识别】计算 2x + 3 = 11，并写出解题步骤。",
                    "source": str(context.get("source_hint") or "图片上传"),
                    "difficulty": "BASIC",
                    "student_answer": "x = 7",
                    "correct_answer": "x = 4",
                    "error_reason": "移项后符号处理错误，需教师复核。",
                    "analysis": "先两边同时减去 3，得到 2x = 8，再两边同时除以 2。",
                    "knowledge_points": [{"knowledge_point_id": None, "name": "一元一次方程"}],
                    "recognition_notes": "这是 Mock 识别草稿，未读取真实图片内容。",
                }
            elif context.get("task_type") == "targeted_practice":
                quantity = int(context.get("quantity") or 5)
                knowledge_name = str(context.get("knowledge_point_name") or "目标知识点")
                difficulty = str(context.get("target_difficulty") or "MEDIUM")
                structured = {
                    "schema_version": "1.0",
                    "title": str(context.get("title") or "Mock 针对性练习"),
                    "teacher_notes": "Mock 生成草稿，题目、答案和解析必须由教师审核。",
                    "questions": [
                        {
                            "question_key": f"mock-{index + 1}",
                            "stem_markdown": f"围绕{knowledge_name}完成虚构练习 {index + 1}。",
                            "answer_markdown": f"虚构答案 {index + 1}。",
                            "analysis_markdown": "先识别考查知识点，再按规范步骤求解并检查。",
                            "difficulty": difficulty,
                            "knowledge_points": [
                                {"knowledge_point_id": None, "name": knowledge_name}
                            ],
                        }
                        for index in range(quantity)
                    ],
                }
            else:
                structured = self._lesson_plan_result(context)
        return AIResult(
            content=(
                json.dumps(structured, ensure_ascii=False) if structured else "Mock AI response"
            ),
            structured=structured,
            provider_request_id="mock",
            input_tokens=0,
            output_tokens=0,
        )

    def _lesson_plan_result(self, context: dict[str, Any]) -> dict[str, Any]:
        total_minutes = int(context.get("planned_minutes", 120))
        weights = (10, 30, 35, 15, 10)
        durations = [max(1, total_minutes * weight // 100) for weight in weights]
        durations[-1] += total_minutes - sum(durations)
        return {
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

    async def cancel(self, provider_request_id: str) -> bool:
        return provider_request_id == "mock"


class OpenAIResponsesProvider:
    def __init__(self, api_key: str, model: str, max_output_tokens: int) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens

    @property
    def capabilities(self) -> AICapabilities:
        return AICapabilities(text=True, structured_output=True, vision=True, cancellation=False)

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
        response_input: Any = request.prompt
        if request.images:
            content: list[dict[str, Any]] = [{"type": "input_text", "text": request.prompt}]
            for image in request.images:
                encoded = base64.b64encode(image.content).decode("ascii")
                content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:{image.mime_type};base64,{encoded}",
                        "detail": image.detail,
                    }
                )
            response_input = [{"role": "user", "content": content}]
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": request.instructions,
            "input": response_input,
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


class DeepSeekChatProvider:
    def __init__(self, api_key: str, model: str, base_url: str, max_output_tokens: int) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_output_tokens = max_output_tokens

    @property
    def capabilities(self) -> AICapabilities:
        return AICapabilities(text=True, structured_output=True, vision=False, cancellation=False)

    async def generate(self, request: AIRequest) -> AIResult:
        if request.images:
            raise RuntimeError("DeepSeek provider does not support image input")
        schema_instruction = ""
        response_format: dict[str, str] | None = None
        if request.schema:
            response_format = {"type": "json_object"}
            schema_instruction = "\n\n请只输出 JSON，并严格遵循以下 JSON Schema：\n" + json.dumps(
                request.schema, ensure_ascii=False
            )
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.instructions or ""},
                {"role": "user", "content": request.prompt + schema_instruction},
            ],
            "max_tokens": self.max_output_tokens,
            "stream": False,
        }
        if response_format is not None:
            request_kwargs["response_format"] = response_format
        response = await self.client.chat.completions.create(**request_kwargs)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("DeepSeek returned empty content")
        structured = json.loads(content) if request.schema else None
        usage = response.usage
        return AIResult(
            content=content,
            structured=structured,
            provider_request_id=response.id,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    async def cancel(self, provider_request_id: str) -> bool:
        del provider_request_id
        return False


class QwenVisionProvider:
    def __init__(self, api_key: str, model: str, base_url: str, max_output_tokens: int) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_output_tokens = max_output_tokens

    @property
    def capabilities(self) -> AICapabilities:
        return AICapabilities(text=True, structured_output=True, vision=True, cancellation=False)

    async def generate(self, request: AIRequest) -> AIResult:
        if not request.images:
            raise RuntimeError("Qwen vision provider requires at least one image")
        schema_instruction = ""
        response_format: dict[str, str] | None = None
        if request.schema:
            response_format = {"type": "json_object"}
            schema_instruction = "\n\n请只输出 JSON，并严格遵循以下 JSON Schema：\n" + json.dumps(
                request.schema, ensure_ascii=False
            )
        content: list[dict[str, Any]] = [
            {"type": "text", "text": request.prompt + schema_instruction}
        ]
        for image in request.images:
            encoded = base64.b64encode(image.content).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.mime_type};base64,{encoded}"},
                }
            )
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.instructions or ""},
                {"role": "user", "content": content},
            ],
            "stream": False,
            "extra_body": {"enable_thinking": False},
        }
        if response_format is not None:
            request_kwargs["response_format"] = response_format
        else:
            request_kwargs["max_completion_tokens"] = self.max_output_tokens
        response = await self.client.chat.completions.create(**request_kwargs)
        response_content = response.choices[0].message.content
        if not response_content:
            raise RuntimeError("Qwen returned empty content")
        structured = json.loads(response_content) if request.schema else None
        usage = response.usage
        return AIResult(
            content=response_content,
            structured=structured,
            provider_request_id=response.id,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    async def cancel(self, provider_request_id: str) -> bool:
        del provider_request_id
        return False


def configured_ai_model(settings: Settings) -> str | None:
    if settings.ai_provider == "openai":
        return settings.openai_model
    if settings.ai_provider == "deepseek":
        return settings.deepseek_model
    return None


def real_provider_configured(settings: Settings) -> bool:
    if settings.ai_provider == "openai":
        return bool(settings.openai_api_key and settings.openai_model)
    if settings.ai_provider == "deepseek":
        return bool(settings.deepseek_api_key and settings.deepseek_model)
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
    if settings.ai_provider == "deepseek":
        if not settings.deepseek_api_key or not settings.deepseek_model:
            raise RuntimeError("DeepSeek provider requires DEEPSEEK_API_KEY and DEEPSEEK_MODEL")
        return DeepSeekChatProvider(
            settings.deepseek_api_key,
            settings.deepseek_model,
            settings.deepseek_base_url,
            settings.ai_max_output_tokens,
        )
    raise RuntimeError(f"Unsupported AI provider: {settings.ai_provider}")


def configured_vision_model(settings: Settings) -> str | None:
    if settings.vision_ai_provider == "openai":
        return settings.vision_openai_model
    if settings.vision_ai_provider == "qwen":
        return settings.qwen_vision_model
    return None


def real_vision_provider_configured(settings: Settings) -> bool:
    if settings.vision_ai_provider == "openai":
        return bool(settings.openai_api_key and settings.vision_openai_model)
    if settings.vision_ai_provider == "qwen":
        return bool(settings.qwen_api_key and settings.qwen_vision_model and settings.qwen_base_url)
    return False


def create_vision_ai_provider(settings: Settings) -> AIProvider:
    if settings.vision_ai_provider == "mock":
        return MockAIProvider()
    if settings.vision_ai_provider == "openai":
        if not settings.openai_api_key or not settings.vision_openai_model:
            raise RuntimeError(
                "OpenAI vision provider requires OPENAI_API_KEY and VISION_OPENAI_MODEL"
            )
        return OpenAIResponsesProvider(
            settings.openai_api_key,
            settings.vision_openai_model,
            settings.ai_max_output_tokens,
        )
    if settings.vision_ai_provider == "qwen":
        if (
            not settings.qwen_api_key
            or not settings.qwen_vision_model
            or not settings.qwen_base_url
        ):
            raise RuntimeError(
                "Qwen vision provider requires QWEN_API_KEY, QWEN_VISION_MODEL and QWEN_BASE_URL"
            )
        return QwenVisionProvider(
            settings.qwen_api_key,
            settings.qwen_vision_model,
            settings.qwen_base_url,
            settings.ai_max_output_tokens,
        )
    raise RuntimeError(f"Unsupported vision AI provider: {settings.vision_ai_provider}")
