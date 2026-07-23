import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.models.registry import ModelSpec

_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
_PROD_MODEL = _MODEL_DIR / "object_detection.onnx"
_TEST_MODEL = _MODEL_DIR / "test_model.onnx"
_MODEL_EXISTS = _PROD_MODEL.exists() or _TEST_MODEL.exists()


@pytest.fixture(scope="module", autouse=True)
def _ensure_test_model():
    if _PROD_MODEL.exists():
        return
    if _TEST_MODEL.exists():
        return
    os.environ["CI_TEST_MODEL"] = "1"
    import sys
    sys.path.insert(0, str(_MODEL_DIR.parent))
    from scripts.generate_test_model import generate
    generate(str(_TEST_MODEL))


@pytest.mark.skipif(not _MODEL_EXISTS and "CI_TEST_MODEL" not in os.environ,
                    reason="No ONNX model available")
@pytest.mark.asyncio
async def test_yolov8_inference():
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (200, 300), (0, 255, 0), 2)
    cv2.circle(img, (400, 200), 50, (0, 0, 255), 2)

    adapter = YOLOv8Adapter(model_dir=str(_MODEL_DIR))
    model_id = "object_detection" if _PROD_MODEL.exists() else "test_model"
    spec = ModelSpec(model_id=model_id, name="YOLOv8-compact", version="1.0.0", backend="onnx")
    result = await adapter.predict(spec, {"image": img})

    assert result.get("model_loaded", False) is True
    assert "inference_ms" in result
