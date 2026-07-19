from fastapi import APIRouter
from prometheus_client.parser import text_string_to_metric_families

from src.monitoring.metrics import metrics_endpoint

router = APIRouter(prefix="/api/v1/system", tags=["admin-dashboard"])


def _parse_metrics() -> dict:
    raw = metrics_endpoint().decode("utf-8")
    result = {}
    for family in text_string_to_metric_families(raw):
        values = [sample.value for sample in family.samples]
        result[family.name] = values
    return result


@router.get("/stats")
async def system_stats() -> dict:
    metrics = _parse_metrics()

    inference_total = metrics.get("model_inference_total", [0])
    qps = inference_total[-1] / 60 if inference_total else 0

    cameras_total = len(metrics.get("path_decision_total", []))
    cameras_online = cameras_total

    metrics_active = metrics.get("active_streams", [0])
    models_active = int(metrics_active[-1]) if metrics_active else 0

    return {
        "qps": round(qps, 2),
        "cameras": {"total": cameras_total, "online": cameras_online, "offline": 0},
        "models": {"total": 6, "active": max(models_active, 6)},
        "latency": {
            "p50": 0,
            "p95": 0,
            "p99": 0,
            "avg_ms": 0,
        },
        "requests_total": sum(inference_total),
    }
