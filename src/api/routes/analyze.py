import json
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.queue.redis_streams import RedisStreamQueue
from src.core.database import Task, Alert
from src.frame_preprocessor.processor import FramePreprocessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/analyze", tags=["analyze"])

_queue: RedisStreamQueue | None = None
MAX_FRAME_BYTES = 10 * 1024 * 1024

_preprocessor: FramePreprocessor | None = None


def init_queue(queue: RedisStreamQueue) -> None:
    global _queue
    _queue = queue


def init_preprocessor(preprocessor: FramePreprocessor) -> None:
    global _preprocessor
    _preprocessor = preprocessor


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


@router.post("/frame")
async def analyze_frame(
    body: dict,
    sync: bool = Query(False, description="同步模式（调试用）"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if _queue is None:
        raise HTTPException(500, "Queue not initialized")

    frame_raw = body.get("frame", "")
    if len(frame_raw) > MAX_FRAME_BYTES:
        raise HTTPException(413, "Frame too large (max 10MB)")

    if sync:
        orchestrator = getattr(analyze_frame, "_orchestrator", None)
        if orchestrator is None:
            raise HTTPException(500, "Orchestrator not initialized in sync mode")
        body["frame"] = frame_raw
        result = await orchestrator.process(body)
        return result

    task_id = str(uuid.uuid4())
    camera_id = body.get("camera_id", "unknown")

    if _preprocessor is not None:
        image = _decode_frame(frame_raw)
        if image is not None:
            decision = _preprocessor.process(image, camera_id)

            if decision.action == "reject":
                task = Task(
                    id=task_id,
                    camera_id=camera_id,
                    path_taken="rejected",
                    status="rejected",
                    rejection_reason=decision.rejection_reason,
                    alert_count=1,
                )
                session.add(task)
                alert = Alert(
                    task_id=task_id,
                    alert_type="quality_rejected",
                    label=decision.rejection_reason or "unknown",
                    bbox=None,
                    confidence=0.0,
                    verified_by="model",
                    status="pending",
                )
                session.add(alert)
                await session.commit()

                logger.info("Frame %s rejected: %s", task_id, decision.rejection_reason)
                return {"task_id": task_id, "status": "rejected", "reason": decision.rejection_reason}

            if decision.action == "skip":
                task = Task(
                    id=task_id,
                    camera_id=camera_id,
                    path_taken="skipped",
                    status="skipped",
                    rejection_reason=decision.rejection_reason,
                )
                session.add(task)
                await session.commit()

                logger.debug("Frame %s skipped by sampler", task_id)
                return {"task_id": task_id, "status": "skipped", "reason": decision.rejection_reason}

            msg = {
                "task_id": task_id,
                "camera_id": camera_id,
                "frame": frame_raw,
                "scene_type": body.get("scene_type") or (decision.scene.get("scene") if decision.scene else None),
                "model_id": body.get("model_id"),
                "scene_info": decision.scene,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            msg = {
                "task_id": task_id,
                "camera_id": camera_id,
                "frame": frame_raw,
                "scene_type": body.get("scene_type"),
                "model_id": body.get("model_id"),
                "timestamp": datetime.now().isoformat(),
            }
    else:
        msg = {
            "task_id": task_id,
            "camera_id": camera_id,
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
