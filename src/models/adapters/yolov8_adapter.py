import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

from src.models.inference import ModelAdapter
from src.models.registry import ModelSpec

try:
    import onnxruntime
except ImportError:
    onnxruntime = None

logger = logging.getLogger(__name__)


class YOLOv8Adapter(ModelAdapter):
    def __init__(self, model_dir: str = "models") -> None:
        self.model_dir = Path(model_dir)
        self._sessions: dict[str, Any] = {}

    def _load_session(self, model_id: str) -> Any:
        if model_id in self._sessions:
            return self._sessions[model_id]
        model_path = self.model_dir / f"{model_id}.onnx"
        if not model_path.exists():
            logger.warning("ONNX model not found: %s", model_path)
            return None
        if onnxruntime is None:
            logger.warning("onnxruntime not installed")
            return None
        session = onnxruntime.InferenceSession(str(model_path))
        self._sessions[model_id] = session
        return session

    def _preprocess(self, image: np.ndarray) -> tuple[np.ndarray, float]:
        input_size = 640
        h, w = image.shape[:2]
        scale = min(input_size / h, input_size / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = np.ascontiguousarray(
            np.array(image.resize((nw, nh))) if hasattr(image, "resize") else image
        )
        if isinstance(resized, np.ndarray) and resized.shape[:2] != (nh, nw):
            import cv2
            resized = cv2.resize(image, (nw, nh))

        if not isinstance(resized, np.ndarray):
            resized = np.array(resized)

        dw, dh = input_size - nw, input_size - nh
        top, bottom = dh // 2, dh - dh // 2
        left, right = dw // 2, dw - dw // 2
        import cv2
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )
        blob = padded.transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, axis=0)
        return blob, scale

    def _postprocess(
        self, outputs: list[np.ndarray], scale: float, conf_threshold: float = 0.25
    ) -> list[dict]:
        predictions = np.squeeze(outputs[0])
        detections = []
        for pred in predictions:
            scores = pred[4:]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])
            if confidence < conf_threshold:
                continue
            x, y, w, h = pred[:4]
            x, y, w, h = x / scale, y / scale, w / scale, h / scale
            x1, y1 = int(x - w / 2), int(y - h / 2)
            x2, y2 = int(x + w / 2), int(y + h / 2)
            detections.append({
                "bbox": [x1, y1, x2, y2],
                "class_id": class_id,
                "confidence": round(confidence, 4),
            })
        return detections

    async def predict(self, spec: ModelSpec, input_data: Any) -> dict:
        session = self._load_session(spec.model_id)
        if session is None:
            return {"detections": [], "stub": True, "model_loaded": False}

        image = input_data.get("image")
        if image is None:
            logger.warning("No image provided for %s", spec.model_id)
            return {"detections": [], "error": "no_image"}

        blob, scale = self._preprocess(image)
        inputs = [o.name for o in session.get_inputs()]
        outputs = session.run(None, {inputs[0]: blob})
        detections = self._postprocess(outputs, scale)

        return {
            "detections": detections,
            "count": len(detections),
            "model_loaded": True,
        }
