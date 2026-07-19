from fastapi import APIRouter, HTTPException
from prometheus_client.parser import text_string_to_metric_families

import src.api.routes.models as models_module
from src.monitoring.metrics import metrics_endpoint

router = APIRouter(prefix="/api/v1/models", tags=["admin-models"])


def _parse_metrics() -> dict:
    raw = metrics_endpoint().decode("utf-8")
    result = {}
    for family in text_string_to_metric_families(raw):
        values = [sample.value for sample in family.samples]
        result[family.name] = values
    return result


@router.get("/{model_id}/stats")
async def model_stats(model_id: str) -> dict:
    if models_module._registry is None or models_module._registry.get(model_id) is None:
        raise HTTPException(404, f"Model {model_id} not found")

    spec = models_module._registry.get(model_id)
    metrics = _parse_metrics()

    inference_total = metrics.get("model_inference_total", [])
    req_count = sum(1 for v in inference_total if v > 0)

    latency_count = metrics.get("model_inference_latency_seconds_count", [1])
    latency_sum = metrics.get("model_inference_latency_seconds_sum", [0])
    count_val = latency_count[-1] if latency_count else 1
    sum_val = latency_sum[-1] if latency_sum else 0
    avg_ms = round((sum_val / count_val) * 1000, 2) if count_val > 0 else 0.0

    return {
        "model_id": model_id,
        "requests_total": req_count,
        "status": spec.status.value if spec else "unknown",
        "latency": {
            "avg_ms": avg_ms,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
        },
    }
