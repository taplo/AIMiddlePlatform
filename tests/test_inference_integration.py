import cv2
import numpy as np
import pytest

from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.models.registry import ModelSpec


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires model files in models/ directory")
async def test_yolov8_inference():
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (200, 300), (0, 255, 0), 2)
    cv2.circle(img, (400, 200), 50, (0, 0, 255), 2)

    adapter = YOLOv8Adapter(model_dir="models")
    spec = ModelSpec(model_id="object_detection", name="YOLOv8n", version="1.0.0", backend="onnx")
    result = await adapter.predict(spec, {"image": img})

    assert result["model_loaded"] is True
    assert result["count"] >= 0
    assert "inference_ms" in result
