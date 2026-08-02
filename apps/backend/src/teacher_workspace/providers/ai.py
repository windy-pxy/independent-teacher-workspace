from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AICapabilities:
    text: bool
    structured_output: bool
    vision: bool
    cancellation: bool


@dataclass(frozen=True)
class AIRequest:
    prompt: str
    schema: dict[str, Any] | None = None
    image_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class AIResult:
    content: str
    structured: dict[str, Any] | None = None
    provider_request_id: str | None = None


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
        structured = (
            {"mock": True, "prompt_length": len(request.prompt)} if request.schema else None
        )
        return AIResult(
            content="Mock AI response", structured=structured, provider_request_id="mock"
        )

    async def cancel(self, provider_request_id: str) -> bool:
        return provider_request_id == "mock"
