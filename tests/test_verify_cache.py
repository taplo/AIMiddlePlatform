import pytest
import json
import time
import base64
from unittest.mock import MagicMock, patch
import numpy as np
import cv2

from src.pipeline.verify_handler import verify_handler


def _make_frame(height=200, width=300):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[50:150, 100:200] = (255, 255, 255)
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("ascii")


def test_verify_cache_hit_skips_llm():
    """Cache hit returns cached result without calling LLM."""
    import src.pipeline.verify_handler as vh

    mock_cache = MagicMock()
    cached_entry = json.dumps({
        "result": {"verified": True, "reason": "cached_result"},
        "created_at": time.time(),
        "context_hash": "verify:person",
    })
    mock_cache.get.return_value = cached_entry.encode()
    mock_cache.zadd.return_value = 1
    mock_cache.expire.return_value = True
    mock_cache.incr.return_value = 1
    vh._verify_cache = mock_cache
    vh._verify_hasher = None

    _orig_client = vh._verify_client
    vh._verify_client = MagicMock()

    try:
        result = verify_handler(
            {"frame": _make_frame(), "camera_id": "cam-1"},
            {"detections": [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        assert result["detections"][0].get("verification_cache_hit"), "should have cache_hit flag"
        assert result["detections"][0]["verified"] is True
        assert result["detections"][0]["verification_reason"] == "cached_result"
        vh._verify_client.assert_not_called()
    finally:
        vh._verify_client = _orig_client
        vh._verify_cache = None


def test_verify_cache_miss_calls_llm():
    """Cache miss falls through to LLM call."""
    import httpx
    from src.agent.client import QwenVLClient
    import src.pipeline.verify_handler as vh

    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    vh._verify_cache = mock_cache
    vh._verify_hasher = None

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "reason": "llm_result"}',
            "role": "assistant",
        }}]
    }))
    _orig = vh._verify_client
    vh._verify_client = QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport))

    try:
        result = verify_handler(
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
