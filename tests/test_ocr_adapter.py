import numpy as np
import pytest

from src.models.adapters.ocr_adapter import OCROnnxAdapter
from src.models.registry import ModelSpec


@pytest.mark.asyncio
async def test_ocr_adapter_no_model_graceful() -> None:
    adapter = OCROnnxAdapter(model_dir="/tmp/nonexistent_models")
    spec = ModelSpec(model_id="ocr_model", name="OCR", version="1.0.0")

    result = await adapter.predict(spec, {})
    assert result["model_loaded"] is False
    assert result["texts"] == []


@pytest.mark.asyncio
async def test_ocr_adapter_invalid_image_format() -> None:
    adapter = OCROnnxAdapter(model_dir="/tmp/nonexistent_models")
    spec = ModelSpec(model_id="ocr_model", name="OCR", version="1.0.0")

    result = await adapter.predict(spec, {"image": "not_an_array"})
    assert "error" in result or result["model_loaded"] is False


@pytest.mark.asyncio
async def test_ocr_adapter_initialization() -> None:
    adapter = OCROnnxAdapter(model_dir="/tmp/models")
    assert adapter.model_dir.name == "models"
