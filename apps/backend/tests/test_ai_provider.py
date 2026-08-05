from types import SimpleNamespace
from typing import Any

import pytest

from teacher_workspace.providers.ai import (
    AIImageInput,
    AIRequest,
    DeepSeekChatProvider,
    OpenAIResponsesProvider,
)


class FakeCompletions:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(
            id="fictional-deepseek-request",
            choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"value":"ok"}'))
            ],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
        )


@pytest.mark.asyncio
async def test_deepseek_provider_uses_json_mode_without_network() -> None:
    provider = DeepSeekChatProvider(
        api_key="fictional-key",
        model="fictional-model",
        base_url="https://api.deepseek.com",
        max_output_tokens=500,
    )
    completions = FakeCompletions()
    provider.client = SimpleNamespace(  # type: ignore[assignment]
        chat=SimpleNamespace(completions=completions)
    )

    result = await provider.generate(
        AIRequest(
            prompt="整理反馈",
            instructions="只依据输入",
            schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        )
    )

    assert result.structured == {"value": "ok"}
    assert result.provider_request_id == "fictional-deepseek-request"
    assert completions.request is not None
    assert completions.request["response_format"] == {"type": "json_object"}
    assert completions.request["model"] == "fictional-model"
    assert "JSON Schema" in completions.request["messages"][1]["content"]


class FakeResponses:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(
            id="fictional-openai-request",
            output_text='{"value":"recognized"}',
            usage=SimpleNamespace(input_tokens=8, output_tokens=3),
        )


@pytest.mark.asyncio
async def test_openai_responses_provider_sends_image_as_private_data_url() -> None:
    provider = OpenAIResponsesProvider("fictional-key", "fictional-vision-model", 500)
    responses = FakeResponses()
    provider.client = SimpleNamespace(responses=responses)  # type: ignore[assignment]

    result = await provider.generate(
        AIRequest(
            prompt="识别虚构题图",
            instructions="只提取可见内容",
            schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            images=(AIImageInput(mime_type="image/png", content=b"fictional"),),
        )
    )

    assert result.structured == {"value": "recognized"}
    assert responses.request is not None
    assert responses.request["store"] is False
    image_part = responses.request["input"][0]["content"][1]
    assert image_part["type"] == "input_image"
    assert image_part["image_url"].startswith("data:image/png;base64,")
