import uuid

from fastapi import APIRouter

from src.core.schemas import StreamConfig, StreamTask
from src.queue import RedisStreamQueue

_queue: RedisStreamQueue | None = None


def init_queue(q: RedisStreamQueue) -> None:
    global _queue
    _queue = q


router = APIRouter(prefix="/api/v1", tags=["ingestion"])

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
    if _queue is not None:
        await _queue.push(camera_id, task.model_dump_json().encode())
    _streams[camera_id] = task
    return task


@router.get("/streams")
async def list_streams() -> list[StreamTask]:
    return list(_streams.values())
