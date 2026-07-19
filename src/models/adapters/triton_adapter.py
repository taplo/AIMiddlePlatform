import logging
from typing import Any

from src.models.inference import ModelAdapter
from src.models.registry import ModelSpec

logger = logging.getLogger(__name__)


class TritonModelAdapter(ModelAdapter):
    def __init__(self, base_url: str = "http://localhost:8001") -> None:
        self.base_url = base_url

    async def predict(self, spec: ModelSpec, input_data: Any) -> Any:
        logger.info("Triton inference: %s (stub)", spec.model_id)
        return {"prediction": None, "stub": True}
