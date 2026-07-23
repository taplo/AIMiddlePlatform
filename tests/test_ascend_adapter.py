import numpy as np
import pytest

from src.models.adapters.ascend_adapter import AscendAdapter
from src.models.inference import ModelAdapter
from src.models.registry import ModelSpec


def test_implements_model_adapter():
    assert issubclass(AscendAdapter, ModelAdapter)


def test_preprocess():
    adapter = AscendAdapter()
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    blob = adapter._preprocess(img, input_size=640)
    assert blob.shape == (1, 3, 640, 640)
    assert blob.dtype == np.float32
    assert blob.max() <= 1.0


def test_postprocess_no_detections():
    adapter = AscendAdapter()
    output = np.zeros((1, 100, 6), dtype=np.float32)
    dets = adapter._postprocess(output, conf_threshold=0.5)
    assert len(dets) == 0


def test_postprocess_with_detections():
    adapter = AscendAdapter()
    output = np.zeros((1, 2, 6), dtype=np.float32)
    output[0, 0] = [10, 20, 100, 200, 0.9, 0.0]
    output[0, 1] = [30, 40, 150, 250, 0.3, 0.0]
    dets = adapter._postprocess(output, conf_threshold=0.5)
    assert len(dets) == 1
    assert dets[0]["label"] == 0
    assert dets[0]["confidence"] == pytest.approx(0.9, abs=1e-6)


@pytest.mark.asyncio
async def test_predict_no_device():
    adapter = AscendAdapter()
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    spec = ModelSpec(model_id="test", name="Test", version="1.0.0")
    result = await adapter.predict(spec, {"image": img})
    assert "error" in result
    assert "preprocess_ok" in result


@pytest.mark.asyncio
async def test_predict_no_image():
    adapter = AscendAdapter()
    spec = ModelSpec(model_id="test", name="Test", version="1.0.0")
    result = await adapter.predict(spec, {})
    assert result.get("error") == "no image in input"
