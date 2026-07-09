import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.api.routes.health import router as health_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes import models as models_route
from src.api.routes import routing as routing_route
from src.api.routes import analyze as analyze_route
from src.api.routes.config_routes import router as config_router
from src.core.config import settings
from src.monitoring.tracing import init_tracing
from src.monitoring.metrics import metrics_endpoint
from src.models.registry import ModelRegistry
from src.models.inference import InferenceOrchestrator
from src.models.presets import register_default_models
from src.models.adapters.onnx_adapter import ONNXModelAdapter
from src.routing.scene_router import SceneRouter
from src.pipeline.registry import PipelineRegistry
from src.pipeline.executor import DAGExecutor
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.routing.fast_path import FastPathHandler
from src.agent.client import QwenVLClient
from src.agent.tools import ToolRegistry, build_cv_tools
from src.agent.agent import CVAgent
from src.agent.orchestrator import AgentOrchestrator
from src.api.routes.admin.auth import router as admin_auth_router
from src.api.routes.admin.auth import get_current_user
from src.api.routes.admin.dashboard import router as admin_dashboard_router
from src.api.routes.admin.models import router as admin_models_router
from src.api.routes.admin.agent import router as admin_agent_router
from src.api.routes.admin.pipelines import router as admin_pipelines_router, init_pipeline_registry
from src.api.routes.admin.logs import router as admin_logs_router
from src.api.routes.admin.traces import router as admin_traces_router
from src.monitoring.log_buffer import init_log_buffer
from src.monitoring.trace_store import init_trace_store
from src.monitoring.tracing import add_trace_store_exporter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_components()
    init_log_buffer(maxlen=2000)
    yield


def _inference_handler(context: dict, input_data: dict) -> dict:
    return {"output": "stub_inference"}


def _init_components() -> None:
    model_registry = ModelRegistry()
    register_default_models(model_registry)
    models_route.init_registry(model_registry)
    logger.info("Initialized model registry with %d models", len(model_registry.list_models()))

    inference = InferenceOrchestrator(model_registry)
    inference.register_adapter("onnx", ONNXModelAdapter())
    logger.info("Initialized inference orchestrator")

    pipeline_registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    _register_default_pipelines(pipeline_registry)
    logger.info("Registered %d pipelines", len(pipeline_registry.list()))
    init_pipeline_registry(pipeline_registry)

    scene_router = SceneRouter()
    routing_route.init_router(scene_router)

    fast_path = FastPathHandler(scene_router, pipeline_registry, executor)
    tool_registry = ToolRegistry(inference)
    build_cv_tools(tool_registry)
    agent = CVAgent(QwenVLClient(), tool_registry)
    orchestrator = AgentOrchestrator(fast_path, agent, inference)
    analyze_route.init_orchestrator(orchestrator)
    logger.info("Initialized agent orchestrator")

    store = init_trace_store(maxlen=500)
    add_trace_store_exporter(store)
    logger.info("Initialized trace store")


def _register_default_pipelines(registry: PipelineRegistry) -> None:
    pipelines = {
        "plate_recognition": [
            DAGNode("detect_plate", NodeType.MODEL_INFERENCE, config={"model": "license_plate"}),
        ],
        "object_detection": [
            DAGNode("detect_objects", NodeType.MODEL_INFERENCE, config={"model": "object_detection"}),
        ],
        "face_recognition": [
            DAGNode("detect_faces", NodeType.MODEL_INFERENCE, config={"model": "face_recognition"}),
        ],
        "vehicle_detection": [
            DAGNode("detect_vehicles", NodeType.MODEL_INFERENCE, config={"model": "vehicle_detection"}),
        ],
        "ocr": [
            DAGNode("ocr_text", NodeType.MODEL_INFERENCE, config={"model": "ocr"}),
        ],
    }
    for name, nodes in pipelines.items():
        dag = DAGDefinition(name=name)
        for n in nodes:
            dag.add_node(n)
        registry.register(name, dag)


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

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(models_route.router)
app.include_router(routing_route.router)
app.include_router(config_router)
app.include_router(analyze_route.router)
app.include_router(admin_auth_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_models_router)
app.include_router(admin_agent_router)
app.include_router(admin_pipelines_router)
app.include_router(admin_logs_router)
app.include_router(admin_traces_router)


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/v1/") and request.url.path not in ("/api/v1/auth/login", "/api/v1/auth/refresh"):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return Response('{"detail":"Not authenticated"}', 401, media_type="application/json")
        try:
            token = auth.split(" ", 1)[1]
            get_current_user(token)
        except HTTPException:
            return Response('{"detail":"Invalid token"}', 401, media_type="application/json")
    return await call_next(request)


@app.get("/metrics")
async def get_metrics() -> Response:
    return Response(content=metrics_endpoint(), media_type="text/plain")


FastAPIInstrumentor.instrument_app(app, tracer_provider=init_tracing())
