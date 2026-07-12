import logging
import time
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

DEFAULT_PROMPTS = ["person", "car", "dog", "cat"]


class YOLOWorldAdapter(ModelAdapter):
    def __init__(self, model_dir: str = "models") -> None:
        self.model_dir = Path(model_dir)
        self._sessions: dict[str, Any] = {}

    def _load_session(self, model_id: str) -> Any:
        if model_id in self._sessions:
            return self._sessions[model_id]
        model_path = self.model_dir / f"{model_id}.onnx"
        if not model_path.exists():
            logger.warning("YOLO-World ONNX model not found: %s", model_path)
            return None
        if onnxruntime is None:
            logger.warning("onnxruntime not installed")
            return None
        session = onnxruntime.InferenceSession(str(model_path))
        self._sessions[model_id] = session
        return session

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        import cv2
        input_size = 640
        h, w = image.shape[:2]
        scale = min(input_size / h, input_size / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
        dw, dh = input_size - nw, input_size - nh
        top, bottom = dh // 2, dh - dh // 2
        left, right = dw // 2, dw - dw // 2
        padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        blob = padded.transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.expand_dims(blob, axis=0)

    def _postprocess(self, outputs: list[np.ndarray]) -> dict:
        return {
            "detections": [],
            "count": 0,
            "note": "YOLO-World postprocessing requires model-specific output format",
        }

    async def predict(self, spec: ModelSpec, input_data: Any) -> dict:
        session = self._load_session(spec.model_id)
        if session is None:
            return {"detections": [], "stub": True, "model_loaded": False}

        image = input_data.get("image")
        if image is None:
            return {"detections": [], "error": "no_image"}

        start = time.monotonic()
        blob = self._preprocess(image)
        inputs = {o.name: blob for o in session.get_inputs()}
        outputs = session.run(None, inputs)
        result = self._postprocess(outputs)
        elapsed_ms = (time.monotonic() - start) * 1000

        return {
            "detections": result.get("detections", []),
            "count": result.get("count", 0),
            "model_loaded": True,
            "inference_ms": round(elapsed_ms, 1),
        }
