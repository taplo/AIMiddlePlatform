import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.agent.agent import CVAgent
from src.agent.agent_config import get_config_manager
from src.agent.orchestrator import AgentOrchestrator
from src.agent.tools import ToolRegistry, build_cv_tools
from src.api.deps import init_session_factory
from src.api.routes import alerts as alerts_route
from src.api.routes import analyze as analyze_route
from src.api.routes import api_keys as api_keys_route
from src.api.routes import model_packages as model_packages_route
from src.api.routes import models as models_route
from src.api.routes import routing as routing_route
from src.api.routes import tasks as tasks_route
from src.api.routes import video_cache as video_cache_route
from src.api.routes import ws as ws_route
from src.api.routes.admin.agent import router as admin_agent_router
from src.api.routes.admin.auth import get_current_user
from src.api.routes.admin.auth import router as admin_auth_router
from src.api.routes.admin.dashboard import router as admin_dashboard_router
from src.api.routes.admin.logs import router as admin_logs_router
from src.api.routes.admin.models import router as admin_models_router
from src.api.routes.admin.notifications import router as admin_notifications_router
from src.api.routes.admin.pipelines import init_pipeline_registry
from src.api.routes.admin.pipelines import router as admin_pipelines_router
from src.api.routes.admin.traces import router as admin_traces_router
from src.api.routes.admin_rules import bindings_router as admin_rule_bindings_router
from src.api.routes.admin_rules import rules_router as admin_rules_router
from src.api.routes.config_routes import router as config_router
from src.api.routes.health import router as health_router
from src.api.routes.ingest import router as ingest_router
from src.core.config import settings
from src.core.security import (
    get_api_key_store,
    get_rate_limiter,
    init_security,
    is_admin_path,
    is_business_path,
    is_exempt_path,
)
from src.data.collector import FrameCollector
from src.frame_preprocessor.adaptive_sampler import AdaptiveFrameSampler
from src.frame_preprocessor.processor import FramePreprocessor
from src.frame_preprocessor.quality_filter import FrameQualityFilter
from src.frame_preprocessor.yolo_world import YOLOWorldSceneClassifier
from src.ingestion.video_cache import init_cache as init_video_cache
from src.models.adapters.yolo_world_adapter import YOLOWorldAdapter
from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.models.inference import InferenceOrchestrator
from src.models.package_manager import ModelPackageManager
from src.models.presets import register_default_models
from src.models.registry import ModelRegistry
from src.monitoring.log_buffer import init_log_buffer
from src.monitoring.metrics import metrics_endpoint, request_latency, request_total
from src.monitoring.request_logger import RequestLoggingMiddleware
from src.monitoring.structured_log import setup_json_logging
from src.monitoring.trace_store import init_trace_store
from src.monitoring.tracing import add_trace_store_exporter, init_tracing
from src.notification.sender import register_webhook_callbacks
from src.pipeline.dag import NodeType
from src.pipeline.executor import DAGExecutor
from src.pipeline.registry import PipelineRegistry
from src.pipeline.shared_init import register_dag_handlers, register_default_pipelines
from src.pipeline.verify_handler import verify_handler
from src.queue import RedisStreamQueue
from src.routing.fast_path import FastPathHandler
from src.routing.scene_router import SceneRouter

logger = logging.getLogger(__name__)

_inference_orchestrator: InferenceOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.core.database import init_db
    db_url = os.getenv("DATABASE_URL") or settings.get("database.url") or "sqlite+aiosqlite:///data/aimp.db"
    db_engine = await init_db(db_url, create_tables=False)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    init_session_factory(session_factory)
    setup_json_logging()
    _init_components()
    register_webhook_callbacks()
    init_log_buffer(maxlen=2000)
    from src.core.redis_client import close_redis, get_redis
    try:
        await get_redis()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning("Redis unavailable: %s", e)
    try:
        from src.ws.manager import ConnectionManager
        redis_url = settings.get("queue.redis_url", "redis://localhost:6379/0")
        ws_mgr = ConnectionManager(redis_url)
        ws_route.ws_manager = ws_mgr
        await ws_mgr.start()
        logger.info("WebSocket manager started")
    except Exception as e:
        logger.warning("WebSocket manager unavailable: %s", e)
        ws_route.ws_manager = None

    from src.monitoring.metrics import StatsRingBuffer, inference_latency, inference_total

    _stats_buffer = StatsRingBuffer()

    async def _record_stats() -> None:
        while True:
            await asyncio.sleep(1)
            try:
                inf_total = 0
                for metric in inference_total.collect():
                    for sample in metric.samples:
                        inf_total += int(sample.value)
                qps = inf_total / 60.0

                hist_sample = inference_latency.collect()
                p50 = p95 = p99 = 0.0
                if hist_sample:
                    buckets = {}
                    for sample in hist_sample[0].samples:
                        if sample.name.endswith("_bucket"):
                            le = float(sample.labels.get("le", "0"))
                            buckets[le] = sample.value
                    total = sum(buckets.values())
                    cum = 0
                    for le, count in sorted(buckets.items()):
                        cum += count
                        if total > 0 and cum / total >= 0.50 and p50 == 0:
                            p50 = le
                        if total > 0 and cum / total >= 0.95 and p95 == 0:
                            p95 = le
                        if total > 0 and cum / total >= 0.99 and p99 == 0:
                            p99 = le
                _stats_buffer.push(qps, p50, p95, p99, 0.0)
            except Exception:
                pass

    _stats_task = asyncio.create_task(_record_stats(), name="stats-recorder")
    logger.info("Stats recorder started")

    yield

    _stats_task.cancel()
    try:
        await _stats_task
    except asyncio.CancelledError:
        pass
    logger.info("Stats recorder stopped")
    if ws_route.ws_manager is not None:
        await ws_route.ws_manager.stop()
        logger.info("WebSocket manager stopped")
    await close_redis()


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
    global _inference_orchestrator
    model_id = node_config.get("model", "")
    if not model_id:
        return {"error": "no model_id in node_config"}
    raw = context.get("frame")
    if raw is None:
        return {"error": "no frame in context"}
    image = _decode_frame(raw)
    if image is None:
        return {"error": "failed to decode frame"}
    result = await _inference_orchestrator.infer(model_id, {"image": image})
    return result


def _init_components() -> None:
    global _inference_orchestrator
    model_registry = ModelRegistry()
    register_default_models(model_registry)
    models_route.init_registry(model_registry)
    logger.info("Initialized model registry with %d models", len(model_registry.list_models()))

    inference = InferenceOrchestrator(model_registry)
    inference.register_adapter("onnx", YOLOv8Adapter(model_dir="models"))
    inference.register_adapter("onnx", YOLOWorldAdapter(model_dir="models"))
    _inference_orchestrator = inference
    logger.info("Initialized inference orchestrator")

    pipeline_registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    executor.register_handler(NodeType.VERIFY, verify_handler)
    register_dag_handlers(executor)
    register_default_pipelines(pipeline_registry)
    logger.info("Registered %d pipelines", len(pipeline_registry.list()))
    init_pipeline_registry(pipeline_registry)

    scene_router = SceneRouter()
    routing_route.init_router(scene_router)

    fast_path = FastPathHandler(scene_router, pipeline_registry, executor)
    tool_registry = ToolRegistry(inference)
    build_cv_tools(tool_registry)
    agent = CVAgent(get_config_manager().get_client(), tool_registry)
    collector = FrameCollector(output_dir=settings.get("data_collection.output_dir", "data/collected/agent_pairs")) if settings.get("data_collection.enabled", False) else None
    orchestrator = AgentOrchestrator(fast_path, agent, inference, collector=collector)
    from src.api.routes.analyze import analyze_frame
    analyze_frame._orchestrator = orchestrator
    logger.info("Initialized agent orchestrator")

    store = init_trace_store(maxlen=500)
    add_trace_store_exporter(store)
    logger.info("Initialized trace store")

    queue = RedisStreamQueue()
    analyze_route.init_queue(queue)
    logger.info("Initialized RedisStreamQueue")

    preprocessor = FramePreprocessor(
        quality_filter=FrameQualityFilter(),
        sampler=AdaptiveFrameSampler(),
        scene_classifier=YOLOWorldSceneClassifier(model_dir="models"),
    )
    analyze_route.init_preprocessor(preprocessor)
    logger.info("Initialized frame preprocessor")

    init_video_cache(default_duration=30.0, max_memory=500 * 1024 * 1024)
    logger.info("Initialized video cache")

    pkg_mgr = ModelPackageManager(Path("models/packages"))
    model_packages_route.init_package_manager(pkg_mgr)
    logger.info("Initialized model package manager")

    init_security()
    logger.info("Initialized security layer")


app = FastAPI(
    title="AI Algorithm Scheduling Platform",
    version="0.1.0",
    description="大小模型协同的 CV 算法调度中台",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    request_total.labels(method=request.method, path=request.url.path, status=response.status_code).inc()
    request_latency.labels(method=request.method, path=request.url.path).observe(elapsed)
    return response


app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(models_route.router)
app.include_router(routing_route.router)
app.include_router(config_router)
app.include_router(analyze_route.router)
app.include_router(tasks_route.router)
app.include_router(admin_auth_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_models_router)
app.include_router(admin_agent_router)
app.include_router(admin_pipelines_router)
app.include_router(admin_logs_router)
app.include_router(admin_traces_router)
app.include_router(admin_notifications_router)
app.include_router(video_cache_route.router)
app.include_router(alerts_route.router)
app.include_router(admin_rules_router)
app.include_router(admin_rule_bindings_router)
app.include_router(api_keys_route.router)
app.include_router(ws_route.router)
app.include_router(model_packages_route.router)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if is_exempt_path(path) or not (is_admin_path(path) or is_business_path(path)):
        return await call_next(request)

    requires_admin = is_admin_path(path)
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")

    if auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ", 1)[1]
            get_current_user(token)
        except HTTPException:
            return Response('{"detail":"Invalid token"}', 401, media_type="application/json")
        return await call_next(request)

    if api_key:
        if requires_admin:
            return Response('{"detail":"Admin access requires JWT, not API key"}', 403, media_type="application/json")
        store = get_api_key_store()
        info = store.validate(api_key)
        if info is None:
            return Response('{"detail":"Invalid API key"}', 401, media_type="application/json")
        limiter = get_rate_limiter()
        allowed, remaining = await limiter.check(api_key, info["rate_per_second"])
        if not allowed:
            return Response(
                '{"detail":"Rate limit exceeded"}',
                429,
                media_type="application/json",
                headers={"Retry-After": "1"},
            )
        resp = await call_next(request)
        resp.headers["X-RateLimit-Remaining"] = str(remaining)
        return resp

    return Response('{"detail":"Authentication required"}', 401, media_type="application/json")


@app.get("/metrics")
async def get_metrics() -> Response:
    return Response(content=metrics_endpoint(), media_type="text/plain")


frontend_dist = (Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

FastAPIInstrumentor.instrument_app(app, tracer_provider=init_tracing())
