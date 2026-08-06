from types import SimpleNamespace
from typing import Any

import pytest

from teacher_workspace.config import Settings
from teacher_workspace.providers.ai import (
    AIImageInput,
    AIRequest,
    DeepSeekChatProvider,
    OpenAIResponsesProvider,
    QwenVisionProvider,
    create_vision_ai_provider,
    real_vision_provider_configured,
)


class FakeCompletions:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(
            id="fictional-deepseek-request",
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"value":"ok"}'))],
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


@pytest.mark.asyncio
async def test_qwen_vision_provider_uses_private_image_and_json_mode() -> None:
    provider = QwenVisionProvider(
        api_key="fictional-key",
        model="fictional-qwen-vision-model",
        base_url="https://fictional-workspace.example/compatible-mode/v1",
        max_output_tokens=500,
    )
    completions = FakeCompletions()
    provider.client = SimpleNamespace(  # type: ignore[assignment]
        chat=SimpleNamespace(completions=completions)
    )

    result = await provider.generate(
        AIRequest(
            prompt="识别虚构题图",
            instructions="只提取可见内容并输出 JSON",
            schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            images=(AIImageInput(mime_type="image/jpeg", content=b"fictional"),),
        )
    )

    assert result.structured == {"value": "ok"}
    assert completions.request is not None
    assert completions.request["response_format"] == {"type": "json_object"}
    assert completions.request["extra_body"] == {"enable_thinking": False}
    assert "max_completion_tokens" not in completions.request
    user_content = completions.request["messages"][1]["content"]
    assert "JSON Schema" in user_content[0]["text"]
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_qwen_vision_provider_factory_requires_complete_server_config() -> None:
    settings = Settings(
        session_secret="x" * 32,
        vision_ai_provider="qwen",
        qwen_api_key="fictional-key",
        qwen_vision_model="fictional-model",
        qwen_base_url="https://fictional-workspace.example/compatible-mode/v1",
    )
    assert real_vision_provider_configured(settings) is True
    assert isinstance(create_vision_ai_provider(settings), QwenVisionProvider)

    incomplete = Settings(
        session_secret="x" * 32,
        vision_ai_provider="qwen",
        qwen_vision_model="fictional-model",
    )
    assert real_vision_provider_configured(incomplete) is False
    with pytest.raises(RuntimeError, match="QWEN_API_KEY"):
        create_vision_ai_provider(incomplete)
