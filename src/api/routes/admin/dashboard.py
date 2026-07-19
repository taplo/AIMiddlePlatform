from fastapi import APIRouter

from src.ingestion.stream_manager import get_manager
from src.monitoring.metrics import get_stats_buffer, inference_latency, inference_total, path_decision_total

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

    fast_path_count = 0
    agent_path_count = 0
    for metric in path_decision_total.collect():
        for sample in metric.samples:
            path_name = sample.labels.get("path", "")
            if path_name == "fast":
                fast_path_count += int(sample.value)
            elif path_name == "agent":
                agent_path_count += int(sample.value)
    total_path = fast_path_count + agent_path_count
    fast_path_pct = round(fast_path_count / total_path * 100, 1) if total_path > 0 else 0.0
    agent_path_pct = round(agent_path_count / total_path * 100, 1) if total_path > 0 else 0.0

    return {
        "total_streams": mgr_stats["total_streams"],
        "active_tasks": mgr_stats["active_tasks"],
        "connected": mgr_stats["connected"],
        "total_frames_kept": mgr_stats["total_frames_kept"],
        "requests_total": inf_total,
        "latency_p99_ms": round(p99 * 1000, 2),
        "fast_path_pct": fast_path_pct,
        "agent_path_pct": agent_path_pct,
        "gpu_util_pct": 0.0,
        "gpu_memory_pct": 0.0,
        "streams": mgr_stats["streams"],
    }


@router.get("/stats/history")
async def system_stats_history() -> dict:
    buf = get_stats_buffer()
    return buf.to_dict()
