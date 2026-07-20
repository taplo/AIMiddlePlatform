import asyncio
import json
import logging
from typing import Any

from prometheus_client import Counter, Histogram, start_http_server
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.agent.agent import CVAgent
from src.agent.client import QwenVLClient
from src.agent.orchestrator import AgentOrchestrator
from src.agent.tools import ToolRegistry, build_cv_tools
from src.core.config import settings
from src.core.database import Task
from src.ingestion.video_cache import get_cache as get_video_cache
from src.models.adapters.yolo_world_adapter import YOLOWorldAdapter
from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.models.inference import InferenceOrchestrator
from src.models.presets import register_default_models
from src.models.registry import ModelRegistry
from src.monitoring.structured_log import setup_json_logging
from src.pipeline.dag import NodeType
from src.pipeline.executor import DAGExecutor
from src.pipeline.registry import PipelineRegistry
from src.pipeline.shared_init import register_dag_handlers, register_default_pipelines
from src.pipeline.verify_handler import verify_handler
from src.queue.redis_streams import RedisStreamQueue
from src.routing.fast_path import FastPathHandler
from src.routing.scene_router import SceneRouter
from src.ws import publish as ws_publish

logger = logging.getLogger(__name__)

worker_tasks_total = Counter("worker_tasks_total", "Total tasks processed by worker", labelnames=["status"])
worker_tasks_latency = Histogram("worker_tasks_latency_seconds", "Worker task processing latency", buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0))


def _extract_detections(results: dict | None) -> list[dict]:
    """Extract flat list of detections from DAG execution results."""
    dets: list[dict] = []
    if isinstance(results, dict):
        all_dets = results.get("all_detections", [])
        if all_dets and isinstance(all_dets, list):
            dets.extend(all_dets)
        for v in results.values():
            if isinstance(v, dict) and "detections" in v:
                dets.extend(v["detections"])
    return dets


async def _evaluate_rules_for_task(
    db_engine: AsyncEngine, task_id: str, camera_id: str, result: dict
) -> None:
    try:
        from src.core.database import Alert, Rule, RuleBinding
        from src.pipeline.rule_engine import CameraRuleState, Detection, RuleEngine

        engine = RuleEngine()
        state = CameraRuleState()

        detections = _extract_detections(result)
        detection_objects = [
            Detection(
                bbox=tuple(d["bbox"]),
                confidence=d.get("confidence", 0.0),
                label=d.get("label", "unknown"),
                track_id=d.get("track_id"),
            )
            for d in detections if isinstance(d, dict) and "bbox" in d
        ]

        async with AsyncSession(db_engine) as session:
            stmt = select(RuleBinding).where(RuleBinding.enabled)
            bindings = (await session.execute(stmt)).scalars().all()

            created_alerts: list[tuple[Alert, Any]] = []

            for binding in bindings:
                if binding.camera_id and binding.camera_id != camera_id:
                    continue
                if not binding.camera_id and binding.scene_type and binding.scene_type != result.get("scene_type"):
                    continue

                rule = await session.get(Rule, binding.rule_id)
                if not rule or not rule.enabled:
                    continue

                result_eval = engine.evaluate(rule, binding, camera_id, detection_objects, state)
                if result_eval and result_eval.triggered:
                    dup_check = select(Alert).where(Alert.task_id == task_id, Alert.rule_id == rule.id)
                    existing = (await session.execute(dup_check)).scalars().first()
                    if existing:
                        continue

                    alert = Alert(
                        task_id=task_id,
                        alert_type=result_eval.rule_type,
                        label=rule.name,
                        bbox=json.dumps(result_eval.matches) if result_eval.matches else None,
                        confidence=max((d.confidence for d in detection_objects), default=0.0),
                        verified_by="model",
                        status="pending",
                        rule_id=rule.id,
                        binding_id=binding.id,
                        metadata_=json.dumps(result_eval.details),
                    )
                    session.add(alert)
                    created_alerts.append((alert, rule))

            await session.commit()

            if settings.get("websocket.enabled", True):
                for alert_obj, rule_obj in created_alerts:
                    try:
                        await ws_publish("ws:alert", {
                            "alert_id": alert_obj.id,
                            "rule_name": rule_obj.name,
                            "camera_id": camera_id,
                            "severity": getattr(rule_obj, "severity", "medium"),
                            "message": f"{rule_obj.name}: triggered on camera {camera_id}",
                        })
                    except Exception:
                        logger.warning("Failed to publish alert %d", alert_obj.id)
    except Exception:
        logger.exception("rule evaluation: failed for task %s camera %s", task_id, camera_id)


def _init_inference() -> InferenceOrchestrator:
    registry = ModelRegistry()
    register_default_models(registry)
    inference = InferenceOrchestrator(registry)
    inference.register_adapter("onnx", YOLOv8Adapter(model_dir="models"))
    inference.register_adapter("onnx", YOLOWorldAdapter(model_dir="models"))
    return inference


def _init_fast_path() -> tuple[SceneRouter, PipelineRegistry, DAGExecutor, FastPathHandler]:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    executor.register_handler(NodeType.VERIFY, verify_handler)
    register_dag_handlers(executor)
    register_default_pipelines(registry)
    handler = FastPathHandler(router, registry, executor)
    return router, registry, executor, handler


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


async def _inference_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    model_id = node_config.get("model", "")
    if not model_id:
        return {"error": "no model_id in node_config"}
    raw = context.get("frame")
    if raw is None:
        return {"error": "no frame in context"}
    image = _decode_frame(raw)
    if image is None:
        return {"error": "failed to decode frame"}
    result = await _inference.infer(model_id, {"image": image})
    return result


_inference: InferenceOrchestrator | None = None


class Worker:
    def __init__(self, db_engine: AsyncEngine, max_concurrent: int = 10, db_queue_size: int = 200, rule_queue_size: int = 200):
        self.db = db_engine
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._db_queue: asyncio.Queue = asyncio.Queue(maxsize=db_queue_size)
        self._rule_queue: asyncio.Queue = asyncio.Queue(maxsize=rule_queue_size)
        global _inference
        _inference = _init_inference()
        _, _, _, self.fast_path = _init_fast_path()
        tool_registry = ToolRegistry(_inference)
        build_cv_tools(tool_registry)
        agent = CVAgent(QwenVLClient(), tool_registry)
        self.orchestrator = AgentOrchestrator(self.fast_path, agent, _inference)

    async def _db_worker(self) -> None:
        while True:
            task_id, camera_id, result = await self._db_queue.get()
            try:
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
            except Exception:
                logger.exception("_db_worker: failed for task %s camera %s", task_id, camera_id)
            finally:
                self._db_queue.task_done()

    async def _rule_worker(self) -> None:
        eval_sem = asyncio.Semaphore(2)
        while True:
            task_id, camera_id, result = await self._rule_queue.get()
            try:
                async with eval_sem:
                    await _evaluate_rules_for_task(self.db, task_id, camera_id, result)
            except Exception:
                logger.exception("_rule_worker: failed for task %s", task_id)
            finally:
                self._rule_queue.task_done()

    async def process_one(self, message: dict) -> dict:
        task_id = message.get("task_id", "unknown")
        camera_id = message.get("camera_id", "unknown")
        start = asyncio.get_event_loop().time()

        frame_raw = message.get("frame", "")
        image = await asyncio.to_thread(_decode_frame, frame_raw) if frame_raw else None

        result = await self.fast_path.process(message)

        latency = (asyncio.get_event_loop().time() - start) * 1000
        worker_tasks_total.labels(status="success" if result is not None else "error").inc()
        worker_tasks_latency.observe(latency / 1000)
        if result is None:
            result = await self.orchestrator.agent.analyze(message, image_data=image)
            result.setdefault("latency_ms", latency)
        else:
            result.setdefault("latency_ms", latency)

        if image is not None:
            try:
                cache = get_video_cache()
                cache.push(camera_id, image, task_id=task_id, metadata={
                    "path": result.get("path", "unknown"),
                    "detection_count": len(result.get("results", {}).get("detections", [])) if isinstance(result.get("results"), dict) else 0,
                })
            except Exception:
                logger.warning("Failed to cache frame for %s", camera_id)

        await self._enqueue_save(task_id, camera_id, result)
        return result

    async def _enqueue_save(self, task_id: str, camera_id: str, result: dict) -> None:
        if settings.get("websocket.enabled", True):
            detections = []
            if isinstance(result, dict):
                all_dets = result.get("all_detections", [])
                if all_dets and isinstance(all_dets, list):
                    detections = all_dets
                else:
                    for v in result.values():
                        if isinstance(v, dict) and "detections" in v:
                            detections.extend(v["detections"])
            await ws_publish("ws:analysis_result", {
                "task_id": task_id,
                "camera_id": camera_id,
                "status": "completed",
                "path_taken": result.get("path", "unknown"),
                "latency_ms": int(result.get("latency_ms", 0)),
                "detections": detections,
                "result": result,
            })

        entry = (task_id, camera_id, result)
        try:
            self._db_queue.put_nowait(entry)
        except asyncio.QueueFull:
            try:
                await asyncio.wait_for(self._db_queue.put(entry), timeout=5.0)
            except TimeoutError:
                logger.warning("db_queue full, skipping DB save for task %s camera %s", task_id, camera_id)

        try:
            self._rule_queue.put_nowait(entry)
        except asyncio.QueueFull:
            try:
                await asyncio.wait_for(self._rule_queue.put(entry), timeout=5.0)
            except TimeoutError:
                logger.warning("rule_queue full, skipping rule eval for task %s camera %s", task_id, camera_id)

    async def _process_with_semaphore(self, raw: str) -> None:
        async with self._semaphore:
            try:
                msg = json.loads(raw)
                await self.process_one(msg)
            except Exception:
                logger.exception("Failed to process message")


def _start_metrics_server(port: int = 8200) -> None:
    try:
        start_http_server(port)
        logger.info("Worker metrics server started on port %d", port)
    except Exception as e:
        logger.warning("Failed to start worker metrics server: %s", e)


async def run_worker(db_url: str = "sqlite+aiosqlite:///data/aimp.db"):
    _start_metrics_server()
    from src.core.database import init_db
    db = await init_db(db_url)
    worker = Worker(
        db,
        max_concurrent=settings.get("worker.max_concurrent", 10),
        db_queue_size=settings.get("worker.db_queue_size", 200),
        rule_queue_size=settings.get("worker.rule_queue_size", 200),
    )
    queue = RedisStreamQueue()

    asyncio.create_task(worker._db_worker(), name="db-worker")
    asyncio.create_task(worker._rule_worker(), name="rule-worker")

    logger.info("Worker started (max_concurrent=%d), consuming from aimp:tasks", worker._semaphore._value)
    async for raw in queue.consume("aimp:tasks"):
        asyncio.create_task(worker._process_with_semaphore(raw))


if __name__ == "__main__":
    setup_json_logging()
    asyncio.run(run_worker())
