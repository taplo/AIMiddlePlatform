import logging
import time
from typing import Any

from src.pipeline.executor import DAGExecutor
from src.pipeline.registry import PipelineRegistry
from src.routing.scene_router import SceneRouter

logger = logging.getLogger(__name__)


class FastPathHandler:
    def __init__(
        self,
        router: SceneRouter,
        registry: PipelineRegistry,
        executor: DAGExecutor,
    ) -> None:
        self.router = router
        self.registry = registry
        self.executor = executor

    async def process(self, frame_context: dict) -> dict[str, Any] | None:
        pipeline_name = self.router.resolve(frame_context)
        if pipeline_name is None:
            try:
                from src.monitoring.metrics import path_decision_total
                camera_id = frame_context.get("camera_id", "unknown")
                path_decision_total.labels(path="unmatched", camera_id=camera_id).inc()
            except Exception:
                pass
            return None

        dag = self.registry.get(pipeline_name)
        if dag is None:
            logger.warning("Pipeline not found: %s", pipeline_name)
            return None

        start = time.monotonic()
        results = await self.executor.execute(dag, frame_context)
        elapsed = time.monotonic() - start
        try:
            from src.monitoring.metrics import path_decision_total
            camera_id = frame_context.get("camera_id", "unknown")
            path_decision_total.labels(path="fast", camera_id=camera_id).inc()
        except Exception:
            pass

        return {
            "path": "fast",
            "pipeline": pipeline_name,
            "results": results,
            "latency_ms": elapsed * 1000,
        }
