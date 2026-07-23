"""Huawei Ascend NPU adapter via CANN (AscendCL).

Requires:
    pip install torch-npu         # PyTorch Ascend backend
    pip install cann-toolkit       # CANN toolkit (optional, for ACL)

Hardware: Ascend 310/310P/910
Model format: .om (offline model) or PyTorch via torch-npu

Usage:
    adapter = AscendAdapter(device_id=0)
    registry.register_adapter("ascend", adapter)
"""

import importlib
import logging
from pathlib import Path
from typing import Any

import numpy as np

from src.models.inference import ModelAdapter
from src.models.registry import ModelSpec

logger = logging.getLogger(__name__)

_has_torch = importlib.util.find_spec("torch") is not None
_has_torch_npu = importlib.util.find_spec("torch_npu") is not None
_has_acl = importlib.util.find_spec("acl") is not None

if _has_torch:
    import torch


class AscendAdapter(ModelAdapter):
    """Inference adapter for Huawei Ascend NPU via CANN.

    Falls back gracefully when hardware or libs are unavailable.
    """

    def __init__(self, model_dir: str = "models", device_id: int = 0):
        self.model_dir = Path(model_dir)
        self.device_id = device_id
        self._models: dict[str, Any] = {}

    def _preprocess(self, image: np.ndarray, input_size: int = 640) -> np.ndarray:
        import cv2
        h, w = image.shape[:2]
        scale = min(input_size / h, input_size / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)

        dw = input_size - nw
        dh = input_size - nh
        top, bottom = dh // 2, dh - dh // 2
        left, right = dw // 2, dw - dw // 2
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )
        blob = padded.transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.expand_dims(blob, axis=0)

    def _postprocess(
        self,
        output: np.ndarray,
        conf_threshold: float = 0.25,
    ) -> list[dict[str, Any]]:
        detections: list[dict[str, Any]] = []
        if output.ndim == 3:
            output = output[0]
        for det in output:
            scores = det[4:]
            max_score = float(scores.max())
            if max_score < conf_threshold:
                continue
            label = int(scores.argmax())
            x1, y1, x2, y2 = det[:4]
            detections.append({
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "label": label,
                "confidence": max_score,
            })
        return detections

    def _check_device(self) -> bool:
        if not _has_torch_npu:
            logger.warning("torch_npu not installed — Ascend inference unavailable")
            return False
        if not _has_torch:
            logger.warning("torch not installed — Ascend inference unavailable")
            return False
        if not torch.npu.is_available():
            logger.warning("No Ascend NPU detected — inference will fail at runtime")
            return False
        return True

    async def predict(self, spec: ModelSpec, input_data: Any) -> dict[str, Any]:
        model_id = spec.model_id
        image = input_data.get("image")
        if image is None:
            return {"error": "no image in input"}

        blob = self._preprocess(image)
        logger.info("Ascend inference: %s (device=%d, input_shape=%s)", model_id, self.device_id, blob.shape)

        if not self._check_device():
            return {
                "error": "Ascend NPU not available",
                "hint": "Install torch_npu and ensure CANN drivers are loaded",
                "model_id": model_id,
                "preprocess_ok": True,
            }

        try:
            input_tensor = torch.from_numpy(blob).npu(self.device_id)
            model = self._models.get(model_id)
            if model is None:
                return {"error": f"model {model_id} not loaded on device {self.device_id}"}

            with torch.no_grad():
                output = model(input_tensor)
            result = output.cpu().numpy()
            detections = self._postprocess(result)
            return {"detections": detections, "model_id": model_id}
        except Exception as e:
            logger.error("Ascend inference failed: %s", e)
            return {"error": str(e), "model_id": model_id}
