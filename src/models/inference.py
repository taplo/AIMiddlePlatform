import asyncio
import logging
import time
from typing import Any

from src.pipeline.executor import DAGExecutor
from src.pipeline.dag import NodeType
from src.models.registry import ModelRegistry, ModelSpec

logger = logging.getLogger(__name__)


class InferenceOrchestrator:
    def __init__(self, model_registry: ModelRegistry) -> None:
        self.model_registry = model_registry
        self._executor = DAGExecutor()
        self._adapters: dict[str, ModelAdapter] = {}

    def register_adapter(self, backend: str, adapter: "ModelAdapter") -> None:
        self._adapters[backend] = adapter

    def get_pipeline_executor(self) -> DAGExecutor:
        return self._executor

    async def infer(self, model_id: str, input_data: Any) -> dict[str, Any]:
        spec = self.model_registry.get(model_id)
        if spec is None:
            raise ValueError(f"Model not found: {model_id}")
        if spec.status.value != "online":
            raise ValueError(f"Model {model_id} is not online")

        adapter = self._adapters.get(spec.backend)
        if adapter is None:
            raise ValueError(f"No adapter for backend: {spec.backend}")

        start = time.monotonic()
        result = await adapter.predict(spec, input_data)
        elapsed = time.monotonic() - start
        logger.info("Model %s inference: %.0fms", model_id, elapsed * 1000)
        try:
            from src.monitoring.metrics import inference_total, inference_latency
            inference_total.labels(model_id=model_id, status="success").inc()
            inference_latency.labels(model_id=model_id).observe(elapsed)
        except Exception:
            pass
        return {
            "model_id": model_id,
            "version": spec.version,
            "output": result,
            "latency_ms": elapsed * 1000,
        }

    async def infer_parallel(
        self, tasks: list[tuple[str, Any]]
    ) -> list[dict[str, Any]]:
        results = await asyncio.gather(
            *[self.infer(model_id, data) for model_id, data in tasks],
            return_exceptions=True,
        )
        return [
            r if isinstance(r, dict) else {"error": str(r)}
            for r in results
        ]


class ModelAdapter:
    async def predict(self, spec: ModelSpec, input_data: Any) -> Any:
        raise NotImplementedError
