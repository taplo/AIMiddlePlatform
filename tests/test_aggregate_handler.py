import pytest
from src.pipeline.aggregate_handler import aggregate_handler


@pytest.mark.asyncio
async def test_aggregate_merges_multiple_sources() -> None:
    result = await aggregate_handler(
        {"frame": b"fake", "camera_id": "cam-1"},
        {
            "detect_objects": {"detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]},
            "detect_faces": {"detections": [{"label": "face", "bbox": [0.1, 0.1, 0.3, 0.3], "confidence": 0.95}]},
        },
        {},
    )
    assert len(result["all_detections"]) == 2
    assert "by_source" in result


@pytest.mark.asyncio
async def test_aggregate_empty_input() -> None:
    result = await aggregate_handler({"frame": b"fake"}, {}, {})
    assert result["all_detections"] == []
    assert result["by_source"] == {}


@pytest.mark.asyncio
async def test_aggregate_respects_max_detections() -> None:
    dets = [{"label": "x", "bbox": [0, 0, 1, 1], "confidence": 0.5} for _ in range(10)]
    result = await aggregate_handler(
        {"frame": b"fake"},
        {"src1": {"detections": list(dets)}},
        {"max_detections": 3},
    )
    assert len(result["all_detections"]) == 3
