import numpy as np
import pytest

from src.pipeline.verify_handler import verify_handler


def _make_frame(height=200, width=300):
    import cv2
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[50:150, 100:200] = (255, 255, 255)
    import base64
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("ascii")


@pytest.mark.asyncio
async def test_verify_no_candidates():
    dets = [
        {"bbox": [0, 0, 10, 10], "label": "car", "confidence": 0.95},
        {"bbox": [0, 0, 10, 10], "label": "bus", "confidence": 0.20},
    ]
    result = await verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    assert result["verification_count"] == 0
    assert all(d.get("verified") is True for d in result["detections"])


@pytest.mark.asyncio
async def test_verify_candidate_triggers_llm_call():
    import httpx

    import src.pipeline.verify_handler as vh
    from src.agent.client import QwenVLClient

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "corrected_label": "person", "reason": "clearly visible"}',
            "role": "assistant",
        }}]
    }))
    _orig = vh._verify_client
    vh._verify_client = QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport))
    vh._verify_cache = None

    try:
        result = await verify_handler(
            {"frame": _make_frame()},
            {"detections": [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        assert result["verification_count"] == 1
        d = result["detections"][0]
        assert d["verified"] is True
        assert d["verification_reason"] != ""
    finally:
        vh._verify_client = _orig
        vh._verify_cache = None


@pytest.mark.asyncio
async def test_verify_empty_frame():
    dets = [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]
    result = await verify_handler(
        {"frame": ""},
        {"detections": dets},
        {},
    )
    assert result["verification_count"] == 0
    assert len(result["detections"]) == 1


@pytest.mark.asyncio
async def test_verify_no_detections():
    result = await verify_handler(
        {"frame": _make_frame()},
        {"detections": []},
        {},
    )
    assert result["verification_count"] == 0
    assert result["detections"] == []


@pytest.mark.asyncio
async def test_verify_edge_threshold():
    import httpx

    import src.pipeline.verify_handler as vh
    from src.agent.client import QwenVLClient

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "corrected_label": "person", "reason": "ok"}',
            "role": "assistant",
        }}]
    }))
    _orig = vh._verify_client
    vh._verify_client = QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport))
    vh._verify_cache = None

    try:
        dets = [
            {"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.5},
            {"bbox": [100, 50, 200, 150], "label": "car", "confidence": 0.8},
            {"bbox": [100, 50, 200, 150], "label": "bus", "confidence": 0.79},
        ]
        result = await verify_handler(
            {"frame": _make_frame()},
            {"detections": dets},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        assert result["verification_count"] == 2
    finally:
        vh._verify_client = _orig
        vh._verify_cache = None
