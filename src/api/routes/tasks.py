import json
import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])

_db_session_factory = None


def init_db_session_factory(factory) -> None:
    global _db_session_factory
    _db_session_factory = factory


@router.get("")
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    camera_id: str | None = Query(None, description="Filter by camera_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        query = select(Task).order_by(Task.created_at.desc())
        count_query = select(sa_func.count()).select_from(Task)
        if status:
            query = query.where(Task.status == status)
            count_query = count_query.where(Task.status == status)
        if camera_id:
            query = query.where(Task.camera_id == camera_id)
            count_query = count_query.where(Task.camera_id == camera_id)

        total = (await session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        rows = (await session.execute(query.offset(offset).limit(page_size))).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "task_id": t.id,
                "camera_id": t.camera_id,
                "status": t.status,
                "path_taken": t.path_taken,
                "latency_ms": t.latency_ms,
                "error_msg": t.error_msg,
                "rejection_reason": t.rejection_reason,
                "alert_count": t.alert_count,
                "created_at": str(t.created_at) if t.created_at else None,
            }
            for t in rows
        ],
    }


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
        "rejection_reason": task.rejection_reason,
        "alert_count": task.alert_count,
        "created_at": str(task.created_at) if task.created_at else None,
    }
