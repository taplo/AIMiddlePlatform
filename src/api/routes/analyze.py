import json
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from src.queue.redis_streams import RedisStreamQueue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/analyze", tags=["analyze"])

_queue: RedisStreamQueue | None = None
MAX_FRAME_BYTES = 10 * 1024 * 1024

_db_session_factory = None


def init_queue(queue: RedisStreamQueue) -> None:
    global _queue
    _queue = queue


def init_db_session_factory(factory) -> None:
    global _db_session_factory
    _db_session_factory = factory


@router.post("/frame")
async def analyze_frame(
    body: dict,
    sync: bool = Query(False, description="同步模式（调试用）"),
) -> dict:
    if _queue is None:
        raise HTTPException(500, "Queue not initialized")

    frame_raw = body.get("frame", "")
    if len(frame_raw) > MAX_FRAME_BYTES:
        raise HTTPException(413, "Frame too large (max 10MB)")

    if sync:
        from src.agent.orchestrator import AgentOrchestrator
        orchestrator = getattr(analyze_frame, "_orchestrator", None)
        if orchestrator is None:
            raise HTTPException(500, "Orchestrator not initialized in sync mode")
        body["frame"] = frame_raw
        result = await orchestrator.process(body)
        return result

    task_id = str(uuid.uuid4())
    msg = {
        "task_id": task_id,
        "camera_id": body.get("camera_id", "unknown"),
        "frame": frame_raw,
        "scene_type": body.get("scene_type"),
        "model_id": body.get("model_id"),
        "timestamp": datetime.now().isoformat(),
    }
    await _queue.push("aimp:tasks", json.dumps(msg).encode())
    return {"task_id": task_id, "status": "queued"}


@router.get("/ping")
async def ping() -> dict:
    return {"ok": True, "timestamp": str(datetime.now())}
