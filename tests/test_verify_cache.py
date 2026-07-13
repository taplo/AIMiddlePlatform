import pytest
import time
from unittest.mock import MagicMock, AsyncMock
import numpy as np
import cv2
import base64

from src.pipeline.verify_handler import verify_handler


def _make_frame(height=200, width=300):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[50:150, 100:200] = (255, 255, 255)
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("ascii")


class FakeCacheResult:
    def __init__(self, result, context_hash):
        self.result = result
        self.context_hash = context_hash
        self.created_at = time.time()


@pytest.mark.asyncio
async def test_verify_cache_hit_skips_llm():
    import src.pipeline.verify_handler as vh

    mock_cache = AsyncMock()
    mock_cache.get.return_value = FakeCacheResult(
        result={"verified": True, "reason": "cached_result"},
        context_hash="verify:person",
    )
    vh._verify_cache = mock_cache

    _orig_client = vh._verify_client
    vh._verify_client = MagicMock()

    try:
        result = await verify_handler(
            {"frame": _make_frame(), "camera_id": "cam-1"},
            {"detections": [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        d = result["detections"][0]
        assert d.get("verification_cache_hit"), "should have cache_hit flag"
        assert d["verified"] is True
        assert d["verification_reason"] == "cached_result"
        vh._verify_client.verify.assert_not_called()
    finally:
        vh._verify_client = _orig_client
        vh._verify_cache = None


@pytest.mark.asyncio
async def test_verify_cache_miss_calls_llm():
    import httpx
    from src.agent.client import QwenVLClient
    import src.pipeline.verify_handler as vh

    mock_cache = AsyncMock()
    mock_cache.get.return_value = None
    vh._verify_cache = mock_cache

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "reason": "llm_result"}',
            "role": "assistant",
        }}]
    }))
    _orig = vh._verify_client
    vh._verify_client = QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport))

    try:
        result = await verify_handler(
            {"frame": _make_frame(), "camera_id": "cam-1"},
            {"detections": [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        assert result["verification_count"] == 1
        d = result["detections"][0]
        assert d["verification_reason"] == "llm_result"
        assert mock_cache.set.called, "should store result in cache"
    finally:
        vh._verify_client = _orig
        vh._verify_cache = None
