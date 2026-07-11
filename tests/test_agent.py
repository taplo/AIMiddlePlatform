import pytest
import httpx
import json

from src.agent.client import (
    QwenVLClient, DeepSeekVLClient,
    LLMError, LLMAPIError, LLMTimeoutError, LLMResponseError,
)


def _mock_transport(response_json: dict, status_code: int = 200):
    return httpx.MockTransport(lambda req: httpx.Response(status_code, json=response_json))


@pytest.mark.asyncio
async def test_qwen_chat_returns_content():
    transport = _mock_transport({
        "choices": [{"message": {"content": "Hello!", "role": "assistant"}}]
    })
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    response = await client.chat([{"role": "user", "content": "hi"}])
    assert response["content"] == "Hello!"
    assert response["tool_calls"] is None


@pytest.mark.asyncio
async def test_qwen_chat_with_tools():
    transport = _mock_transport({
        "choices": [{
            "message": {
                "content": None,
                "role": "assistant",
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "detect_objects", "arguments": '{"image": "base64..."}'}}
                ]
            }
        }]
    })
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    response = await client.chat(
        [{"role": "user", "content": "detect objects"}],
        tools=[{"type": "function", "function": {"name": "detect_objects"}}],
    )
    assert response["tool_calls"] is not None
    assert response["tool_calls"][0]["function"]["name"] == "detect_objects"


@pytest.mark.asyncio
async def test_qwen_chat_with_image():
    transport = _mock_transport({
        "choices": [{"message": {"content": "A traffic scene", "role": "assistant"}}]
    })
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    response = await client.chat_with_image("What is this?", b"fake_image_data")
    assert response["content"] == "A traffic scene"


@pytest.mark.asyncio
async def test_qwen_fallback_json_on_tool_call_failure():
    """When API returns 400 for tools, retry without tools + response_format=json_object"""
    called_first = False

    def handler(req):
        nonlocal called_first
        if not called_first:
            called_first = True
            return httpx.Response(400, json={"error": "tools not supported"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"scene_type": "traffic"}', "role": "assistant"}}]
        })

    client = QwenVLClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    response = await client.chat(
        [{"role": "user", "content": "analyze"}],
        tools=[{"type": "function", "function": {"name": "detect_objects"}}],
    )
    assert response["content"] is not None


@pytest.mark.asyncio
async def test_qwen_raises_on_api_error():
    transport = _mock_transport({"error": "unauthorized"}, status_code=401)
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    with pytest.raises(LLMAPIError, match="401"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_qwen_deepseek_defaults():
    client = DeepSeekVLClient(http_client=httpx.AsyncClient(transport=_mock_transport({
        "choices": [{"message": {"content": "ok", "role": "assistant"}}]
    })))
    response = await client.chat([{"role": "user", "content": "hi"}])
    assert response["content"] == "ok"
