"""Cambricon MLU adapter via neuware (CNRT / CNNL).

Requires:
    pip install torch_mlu         # PyTorch MLU backend (寒武纪)
    # Or use CNRT C++ runtime directly via ctypes

Hardware: Cambricon MLU220/MLU270/MLU370
Model format: .cambricon (offline) or PyTorch via torch_mlu

Usage:
    adapter = CambriconAdapter(device_id=0)
    registry.register_adapter("cambricon", adapter)
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
_has_torch_mlu = importlib.util.find_spec("torch_mlu") is not None

if _has_torch:
    import torch


class CambriconAdapter(ModelAdapter):
    """Inference adapter for Cambricon MLU via torch_mlu.

    Falls back gracefully when hardware or libs are unavailable.
    """

    COCO_CLASSES = [
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
        "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    ]

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
            label_name = self.COCO_CLASSES[label] if label < len(self.COCO_CLASSES) else str(label)
            detections.append({
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "label": label_name,
                "confidence": max_score,
            })
        return detections

    def _check_device(self) -> bool:
        if not _has_torch_mlu:
            logger.warning("torch_mlu not installed — Cambricon inference unavailable")
            return False
        if not _has_torch:
            logger.warning("torch not installed — Cambricon inference unavailable")
            return False
        if not torch.mlu.is_available():
            logger.warning("No Cambricon MLU detected — inference will fail at runtime")
            return False
        return True

    async def predict(self, spec: ModelSpec, input_data: Any) -> dict[str, Any]:
        model_id = spec.model_id
        image = input_data.get("image")
        if image is None:
            return {"error": "no image in input"}

        blob = self._preprocess(image)
        logger.info("Cambricon inference: %s (device=%d, input_shape=%s)", model_id, self.device_id, blob.shape)

        if not self._check_device():
            return {
                "error": "Cambricon MLU not available",
                "hint": "Install torch_mlu and ensure neuware drivers are loaded",
                "model_id": model_id,
                "preprocess_ok": True,
            }

        try:
            input_tensor = torch.from_numpy(blob).mlu(self.device_id)
            model = self._models.get(model_id)
            if model is None:
                return {"error": f"model {model_id} not loaded on device {self.device_id}"}

            with torch.no_grad():
                output = model(input_tensor)
            result = output.cpu().numpy()
            detections = self._postprocess(result)
            return {"detections": detections, "model_id": model_id}
        except Exception as e:
            logger.error("Cambricon inference failed: %s", e)
            return {"error": str(e), "model_id": model_id}
