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


@pytest.mark.asyncio
async def test_yolov8_adapter_with_image() -> None:
    adapter = YOLOv8Adapter(model_dir="models")
    spec = ModelSpec(model_id="yolov8n", name="YOLOv8n", version="1.0.0", backend="onnx")
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    result = await adapter.predict(spec, {"image": img})
    assert result["model_loaded"] is True
    assert "count" in result
    assert "detections" in result
    assert "inference_ms" in result


@pytest.mark.asyncio
async def test_yolov8_adapter_preprocess() -> None:
    adapter = YOLOv8Adapter(model_dir="models")
    img = np.ones((360, 480, 3), dtype=np.uint8) * 128
    blob, scale, pad_left, pad_top = adapter._preprocess(img)
    assert blob.shape == (1, 3, 640, 640)
    assert 0 < scale < 2
    assert pad_left >= 0
    assert pad_top >= 0
