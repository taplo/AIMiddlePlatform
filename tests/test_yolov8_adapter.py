import numpy as np
import pytest

from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.models.registry import ModelSpec


@pytest.mark.asyncio
async def test_yolov8_adapter_no_model_graceful() -> None:
    adapter = YOLOv8Adapter(model_dir="/tmp/nonexistent_models")
    spec = ModelSpec(model_id="yolov8n", name="YOLOv8n", version="1.0.0")

    result = await adapter.predict(spec, {})
    assert result["model_loaded"] is False
    assert result["detections"] == []


@pytest.mark.asyncio
async def test_yolov8_adapter_no_image_graceful() -> None:
    adapter = YOLOv8Adapter(model_dir="/tmp/nonexistent_models")
    spec = ModelSpec(model_id="yolov8n", name="YOLOv8n", version="1.0.0")

    result = await adapter.predict(spec, {"image": None})
    assert result["model_loaded"] is False


@pytest.mark.asyncio
async def test_adapter_initialization() -> None:
    adapter = YOLOv8Adapter(model_dir="/tmp/models")
    assert adapter.model_dir.name == "models"
