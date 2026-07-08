from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.api.routes.health import router as health_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes.models import router as models_router
from src.api.routes.routing import router as routing_router
from src.api.routes.config_routes import router as config_router
from src.api.routes.analyze import router as analyze_router
from src.core.config import settings
from src.monitoring.tracing import init_tracing
from src.monitoring.metrics import metrics_endpoint

app = FastAPI(
    title="AI Algorithm Scheduling Platform",
    version="0.1.0",
    description="大小模型协同的 CV 算法调度中台",
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
app.include_router(models_router)
app.include_router(routing_router)
app.include_router(config_router)
app.include_router(analyze_router)


@app.get("/metrics")
async def get_metrics() -> Response:
    return Response(content=metrics_endpoint(), media_type="text/plain")


FastAPIInstrumentor.instrument_app(app, tracer_provider=init_tracing())
