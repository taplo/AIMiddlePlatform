from fastapi import APIRouter, Query

from src.monitoring.log_buffer import clear_logs, get_logs

router = APIRouter(prefix="/api/v1/logs", tags=["admin-logs"])


@router.get("")
async def query_logs(
    level: str | None = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    module: str | None = Query(None, description="Filter by module name (substring match)"),
    q: str | None = Query(None, description="Search in message text"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    return get_logs(level=level, module=module, q=q, limit=limit, offset=offset)


@router.delete("")
async def delete_logs() -> dict:
    clear_logs()
    return {"ok": True}
