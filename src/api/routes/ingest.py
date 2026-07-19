from fastapi import APIRouter

from src.core.schemas import StreamConfig
from src.ingestion.stream_manager import get_manager

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


@router.post("/analyze/stream")
async def register_stream(config: StreamConfig) -> dict:
    mgr = get_manager()
    session = await mgr.add_stream(
        camera_id=config.camera_id,
        stream_url=config.stream_url,
        protocol=config.protocol,
        target_fps=config.target_fps or 2.0,
    )
    return session.get_info()


@router.get("/streams")
async def list_streams() -> list[dict]:
    mgr = get_manager()
    return mgr.list_streams()


@router.delete("/streams/{camera_id}")
async def remove_stream(camera_id: str) -> dict:
    mgr = get_manager()
    ok = await mgr.remove_stream(camera_id)
    return {"ok": ok}
