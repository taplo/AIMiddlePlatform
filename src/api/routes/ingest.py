import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.core.schemas import AnalysisResult, StreamConfig, StreamTask

router = APIRouter(prefix="/v1", tags=["ingestion"])

_streams: dict[str, StreamTask] = {}


@router.post("/analyze/stream")
async def register_stream(config: StreamConfig) -> StreamTask:
    task_id = str(uuid.uuid4())
    camera_id = f"cam-{uuid.uuid4().hex[:8]}"
    task = StreamTask(
        task_id=task_id,
        camera_id=camera_id,
        stream_url=config.stream_url,
        protocol=config.protocol,
        config=config,
    )
    _streams[camera_id] = task
    return task


@router.get("/tasks/{task_id}/results")
async def get_results(task_id: str) -> AnalysisResult:
    return AnalysisResult(
        request_id=task_id,
        timestamp=datetime.now(),
        camera_id="unknown",
    )


@router.get("/streams")
async def list_streams() -> list[StreamTask]:
    return list(_streams.values())
