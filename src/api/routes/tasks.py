import json

from fastapi import APIRouter, HTTPException

from src.core.database import Task

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])

_db_session_factory = None


def init_db_session_factory(factory) -> None:
    global _db_session_factory
    _db_session_factory = factory


@router.get("/{task_id}/results")
async def get_task_result(task_id: str) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return {
        "task_id": task.id,
        "status": task.status,
        "camera_id": task.camera_id,
        "path_taken": task.path_taken,
        "result": json.loads(task.result_json) if task.result_json else None,
        "latency_ms": task.latency_ms,
        "error": task.error_msg,
        "created_at": str(task.created_at) if task.created_at else None,
    }
