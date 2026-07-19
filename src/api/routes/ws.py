import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from src.ws.auth import validate_ws_token
from src.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])

ws_manager: ConnectionManager | None = None


def get_ws_manager() -> ConnectionManager:
    assert ws_manager is not None, "ConnectionManager not initialized"
    return ws_manager


@router.websocket("")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(...),
    manager: ConnectionManager = Depends(get_ws_manager),
):
    if not validate_ws_token(token):
        await ws.close(code=4001)
        return
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
