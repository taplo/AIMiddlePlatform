import logging
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


class OCROnnxAdapter(ModelAdapter):
    def __init__(self, model_dir: str = "models") -> None:
        self.model_dir = Path(model_dir)
        self._sessions: dict[str, Any] = {}

    def _load_session(self, model_id: str) -> Any:
        if model_id in self._sessions:
            return self._sessions[model_id]
        model_path = self.model_dir / f"{model_id}.onnx"
        if not model_path.exists():
            logger.warning("OCR ONNX model not found: %s", model_path)
            return None
        if onnxruntime is None:
            logger.warning("onnxruntime not installed")
            return None
        session = onnxruntime.InferenceSession(str(model_path))
        self._sessions[model_id] = session
        return session

    async def predict(self, spec: ModelSpec, input_data: Any) -> dict:
        session = self._load_session(spec.model_id)
        if session is None:
            return {"texts": [], "stub": True, "model_loaded": False}

        image = input_data.get("image")
        if image is None:
            return {"texts": [], "error": "no_image"}

        import cv2
        if isinstance(image, np.ndarray):
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        else:
            return {"texts": [], "error": "invalid_image_format"}

        blob = np.expand_dims(np.expand_dims(gray.astype(np.float32) / 255.0, 0), 0)
        inputs = [o.name for o in session.get_inputs()]
        outputs = session.run(None, {inputs[0]: blob})

        raw_text = str(outputs[0][0]) if outputs and len(outputs[0]) > 0 else ""
        return {
            "texts": [{"text": raw_text, "confidence": 0.9}] if raw_text else [],
            "model_loaded": True,
        }
