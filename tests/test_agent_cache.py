from unittest.mock import AsyncMock

import pytest

from src.agent.agent import CVAgent


@pytest.mark.asyncio
async def test_analyze_checks_cache_before_llm() -> None:
    mock_llm = AsyncMock()
    mock_tools = AsyncMock()
    mock_tools.get_openai_specs.return_value = []
    mock_cache = AsyncMock()
    mock_cache.get.return_value = None  # miss -> proceed to LLM

    agent = CVAgent(mock_llm, mock_tools)
    agent._cache = mock_cache

    mock_llm.chat_with_image.return_value = {"content": '{"scene_type": "indoor"}'}
    await agent.analyze(
        {"camera_id": "cam-1"},
        image_data=b"fake_frame_bytes",
    )
    assert mock_cache.get.called
    assert mock_cache.set.called


@pytest.mark.asyncio
async def test_analyze_returns_cached_result() -> None:
    mock_llm = AsyncMock()
    mock_tools = AsyncMock()
    mock_tools.get_openai_specs.return_value = []
    mock_cache = AsyncMock()
    from src.cache.result_cache import CacheResult
    mock_cache.get.return_value = CacheResult(
        result={"path": "agent", "analysis": {"scene_type": "indoor"}, "latency_ms": 10, "tool_results": {}},
        created_at=100.0,
        context_hash="",
    )

    agent = CVAgent(mock_llm, mock_tools)
    agent._cache = mock_cache

    result = await agent.analyze(
        {"camera_id": "cam-1"},
        image_data=b"fake_frame_bytes",
    )
    assert result["analysis"]["scene_type"] == "indoor"
    mock_llm.chat_with_image.assert_not_called()
