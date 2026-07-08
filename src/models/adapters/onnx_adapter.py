import logging
from typing import Any

from src.models.inference import ModelAdapter
from src.models.registry import ModelSpec

logger = logging.getLogger(__name__)


class ONNXModelAdapter(ModelAdapter):
    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}

    async def predict(self, spec: ModelSpec, input_data: Any) -> Any:
        logger.info("ONNX inference: %s (stub)", spec.model_id)
        return {"prediction": None, "stub": True}
