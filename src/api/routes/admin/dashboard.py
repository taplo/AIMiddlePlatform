from fastapi import APIRouter

from src.ingestion.stream_manager import get_manager
from src.monitoring.metrics import get_stats_buffer, inference_latency, inference_total

router = APIRouter(prefix="/api/v1/system", tags=["admin-dashboard"])


@router.get("/stats")
async def system_stats() -> dict:
    mgr = get_manager()
    mgr_stats = mgr.stats()

    inf_total = 0
    for metric in inference_total.collect():
        for sample in metric.samples:
            inf_total += int(sample.value)

    hist_sample = inference_latency.collect()
    p99 = 0.0
    if hist_sample:
        buckets = {}
        for sample in hist_sample[0].samples:
            if sample.name.endswith("_bucket"):
                le = float(sample.labels.get("le", "0"))
                buckets[le] = sample.value
        total = 0
        cum = 0
        for le, count in sorted(buckets.items()):
            total += count
            cum += count
            if total > 0 and cum / total >= 0.99:
                p99 = le
                break

    return {
        "total_streams": mgr_stats["total_streams"],
        "active_tasks": mgr_stats["active_tasks"],
        "connected": mgr_stats["connected"],
        "total_frames_kept": mgr_stats["total_frames_kept"],
        "requests_total": inf_total,
        "latency_p99_ms": round(p99 * 1000, 2),
        "streams": mgr_stats["streams"],
    }


@router.get("/stats/history")
async def system_stats_history() -> dict:
    buf = get_stats_buffer()
    return buf.to_dict()
