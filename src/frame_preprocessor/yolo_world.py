import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

SCENE_PROMPTS = [
    "indoor room", "parking lot", "highway", "intersection",
    "warehouse", "corridor", "outdoor", "office",
    "factory floor", "construction site", "street", "gate",
]


class YOLOWorldSceneClassifier:
    def __init__(self, model_dir: str = "models", model_name: str = "yolo_world"):
        self.model_path = Path(model_dir) / f"{model_name}.onnx"
        self._session = None
        if self.model_path.exists() and onnxruntime is not None:
            try:
                self._session = onnxruntime.InferenceSession(str(self.model_path))
                logger.info("YOLO-World model loaded: %s", self.model_path)
            except Exception as e:
                logger.warning("Failed to load YOLO-World ONNX: %s", e)

    def is_available(self) -> bool:
        return self._session is not None

    def classify(self, image: np.ndarray) -> dict[str, Any]:
        if not self.is_available():
            return {"scene": None, "confidence": 0.0, "available": False}

        try:
            blob = self._preprocess(image)
            inputs = {o.name: blob for o in self._session.get_inputs()}
            outputs = self._session.run(None, inputs)
            return self._postprocess(outputs)
        except Exception as e:
            logger.error("YOLO-World inference error: %s", e)
            return {"scene": None, "confidence": 0.0, "error": str(e)}

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

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        return {
            "scene": None,
            "confidence": 0.0,
            "available": True,
            "note": "YOLO-World postprocessing requires model-specific format",
        }


try:
    import onnxruntime
except ImportError:
    onnxruntime = None
