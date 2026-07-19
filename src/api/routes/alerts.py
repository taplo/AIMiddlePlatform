import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.database import Alert, Task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    status: str | None = Query(None, description="Filter by status"),
    alert_type: str | None = Query(None, description="Filter by alert_type"),
    task_id: str | None = Query(None, description="Filter by task_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Alert).order_by(Alert.created_at.desc())
    count_query = select(sa_func.count()).select_from(Alert)
    if status:
        query = query.where(Alert.status == status)
        count_query = count_query.where(Alert.status == status)
    if alert_type:
        query = query.where(Alert.alert_type == alert_type)
        count_query = count_query.where(Alert.alert_type == alert_type)
    if task_id:
        query = query.where(Alert.task_id == task_id)
        count_query = count_query.where(Alert.task_id == task_id)

    total = (await session.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    rows = (await session.execute(query.offset(offset).limit(page_size))).scalars().all()

    items = []
    for a in rows:
        camera_id = None
        task = await session.get(Task, a.task_id)
        if task:
            camera_id = task.camera_id
        items.append({
            "id": a.id,
            "task_id": a.task_id,
            "camera_id": camera_id,
            "alert_type": a.alert_type,
            "label": a.label,
            "bbox": a.bbox,
            "confidence": a.confidence,
            "verified_by": a.verified_by,
            "status": a.status,
            "created_at": str(a.created_at) if a.created_at else None,
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/{alert_id}")
async def get_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, f"Alert {alert_id} not found")
    return {
        "id": alert.id,
        "task_id": alert.task_id,
        "alert_type": alert.alert_type,
        "label": alert.label,
        "bbox": alert.bbox,
        "confidence": alert.confidence,
        "verified_by": alert.verified_by,
        "status": alert.status,
        "created_at": str(alert.created_at) if alert.created_at else None,
    }
