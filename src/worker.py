import json
import logging
import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy import select

from src.core.database import Task, Alert
from src.queue.redis_streams import RedisStreamQueue
from src.routing.fast_path import FastPathHandler
from src.agent.orchestrator import AgentOrchestrator
from src.models.inference import InferenceOrchestrator
from src.models.registry import ModelRegistry
from src.models.presets import register_default_models
from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.pipeline.registry import PipelineRegistry
from src.pipeline.executor import DAGExecutor
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.routing.scene_router import SceneRouter
from src.agent.tools import ToolRegistry, build_cv_tools
from src.agent.client import QwenVLClient
from src.agent.agent import CVAgent

logger = logging.getLogger(__name__)


def _init_inference() -> InferenceOrchestrator:
    registry = ModelRegistry()
    register_default_models(registry)
    inference = InferenceOrchestrator(registry)
    inference.register_adapter("onnx", YOLOv8Adapter(model_dir="models"))
    return inference


def _init_fast_path() -> tuple[SceneRouter, PipelineRegistry, DAGExecutor, FastPathHandler]:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    _register_default_pipelines(registry)
    handler = FastPathHandler(router, registry, executor)
    return router, registry, executor, handler


def _register_default_pipelines(registry: PipelineRegistry) -> None:
    pipelines = {
        "plate_recognition": [DAGNode("detect_plate", NodeType.MODEL_INFERENCE, config={"model": "license_plate"})],
        "object_detection": [DAGNode("detect_objects", NodeType.MODEL_INFERENCE, config={"model": "object_detection"})],
        "face_recognition": [DAGNode("detect_faces", NodeType.MODEL_INFERENCE, config={"model": "face_recognition"})],
        "vehicle_detection": [DAGNode("detect_vehicles", NodeType.MODEL_INFERENCE, config={"model": "vehicle_detection"})],
        "ocr": [DAGNode("ocr_text", NodeType.MODEL_INFERENCE, config={"model": "ocr"})],
    }
    for name, nodes in pipelines.items():
        dag = DAGDefinition(name=name)
        for n in nodes:
            dag.add_node(n)
        registry.register(name, dag)


def _decode_frame(frame: str):
    import base64
    import cv2
    import numpy as np
    try:
        raw = base64.b64decode(frame)
        arr = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _inference_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    model_id = node_config.get("model", "")
    if not model_id:
        return {"error": "no model_id in node_config"}
    raw = context.get("frame")
    if raw is None:
        return {"error": "no frame in context"}
    image = _decode_frame(raw)
    if image is None:
        return {"error": "failed to decode frame"}
    result = asyncio.run(_inference.infer(model_id, {"image": image}))
    return result


_inference: InferenceOrchestrator | None = None


class Worker:
    def __init__(self, db_engine: AsyncEngine):
        self.db = db_engine
        global _inference
        _inference = _init_inference()
        _, _, _, self.fast_path = _init_fast_path()
        tool_registry = ToolRegistry(_inference)
        build_cv_tools(tool_registry)
        agent = CVAgent(QwenVLClient(), tool_registry)
        self.orchestrator = AgentOrchestrator(self.fast_path, agent, _inference)

    async def process_one(self, message: dict) -> dict:
        task_id = message.get("task_id", "unknown")
        camera_id = message.get("camera_id", "unknown")
        start = asyncio.get_event_loop().time()

        result = await self.fast_path.process(message)

        latency = (asyncio.get_event_loop().time() - start) * 1000
        if result is None:
            frame_raw = message.get("frame", "")
            image = _decode_frame(frame_raw) if frame_raw else None
            result = await self.orchestrator.agent.analyze(message, image_data=image)
            result.setdefault("latency_ms", latency)
        else:
            result.setdefault("latency_ms", latency)

        await self._save_result(task_id, camera_id, result)
        return result

    async def _save_result(self, task_id: str, camera_id: str, result: dict):
        import json
        async with AsyncSession(self.db) as session:
            task = Task(
                id=task_id,
                camera_id=camera_id,
                path_taken=result.get("path", "unknown"),
                status="completed",
                result_json=json.dumps(result, default=str),
                latency_ms=int(result.get("latency_ms", 0)),
            )
            session.add(task)
            await session.commit()


async def run_worker(db_url: str = "sqlite+aiosqlite:///data/aimp.db"):
    from src.core.database import init_db
    db = await init_db(db_url)
    worker = Worker(db)
    queue = RedisStreamQueue()

    logger.info("Worker started, consuming from aimp:tasks")
    async for raw in queue.consume("aimp:tasks"):
        try:
            msg = json.loads(raw)
            await worker.process_one(msg)
        except Exception as e:
            logger.error("Failed to process message: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
