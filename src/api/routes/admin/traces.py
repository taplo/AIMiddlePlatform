from fastapi import APIRouter, HTTPException, Query

from src.monitoring.trace_store import get_traces, get_trace_detail

router = APIRouter(prefix="/api/v1/traces", tags=["admin-traces"])


@router.get("")
async def list_traces(
    min_duration_ms: float = Query(0, ge=0),
    error_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    traces = get_traces(min_duration_ms=min_duration_ms, error_only=error_only, limit=limit)
    return {"traces": traces}


@router.get("/{trace_id}")
async def trace_detail(trace_id: str) -> dict:
    detail = get_trace_detail(trace_id)
    if detail is None:
        raise HTTPException(404, f"Trace '{trace_id}' not found")
    return detail
