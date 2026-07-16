import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from src.ingestion.video_cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/video-cache", tags=["video_cache"])


@router.get("/stats")
async def get_all_stats() -> dict:
    cache = get_cache()
    return {"cameras": cache.all_stats(), "total_memory_bytes": cache.estimate_total_memory()}


@router.get("/{camera_id}")
async def get_camera_stats(camera_id: str) -> dict:
    cache = get_cache()
    stats = cache.stats(camera_id)
    if stats["buffered_frames"] == 0:
        raise HTTPException(404, f"No cache for camera: {camera_id}")
    return stats


@router.put("/{camera_id}/duration")
async def set_duration(camera_id: str, body: dict) -> dict:
    duration = body.get("duration")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise HTTPException(400, "duration must be a positive number")
    cache = get_cache()
    cache.set_duration(camera_id, duration)
    return {"camera_id": camera_id, "duration": cache._get_duration(camera_id)}


@router.get("/{camera_id}/frames")
async def get_recent_frames(camera_id: str, count: int = Query(5, ge=1, le=100)) -> dict:
    cache = get_cache()
    frames = cache.get_recent(camera_id, count=count)
    return {
        "camera_id": camera_id,
        "frames": [
            {
                "timestamp": f.timestamp,
                "task_id": f.task_id,
                "metadata": f.metadata,
                "shape": list(f.data.shape),
            }
            for f in frames
        ],
    }


@router.get("/{camera_id}/segment")
async def get_segment(
    camera_id: str,
    start: float = Query(..., description="Start timestamp (unix)"),
    end: float = Query(..., description="End timestamp (unix)"),
) -> dict:
    cache = get_cache()
    frames = cache.get_segment(camera_id, start, end)
    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "frames": [
            {
                "timestamp": f.timestamp,
                "task_id": f.task_id,
                "metadata": f.metadata,
                "shape": list(f.data.shape),
            }
            for f in frames
        ],
    }


@router.delete("/{camera_id}")
async def clear_cache(camera_id: str) -> dict:
    cache = get_cache()
    cache.clear(camera_id)
    return {"camera_id": camera_id, "status": "cleared"}
