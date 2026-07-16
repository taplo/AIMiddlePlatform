import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from src.api.app import app
from src.ws.manager import ConnectionManager


@pytest.mark.asyncio
async def test_ws_endpoint_valid_token_accepts():
    mock_mgr = MagicMock(spec=ConnectionManager)
    async def fake_connect(ws):
        await ws.accept()
    mock_mgr.connect = AsyncMock(side_effect=fake_connect)
    mock_mgr.disconnect = AsyncMock()
    with patch("src.api.routes.ws.ws_manager", mock_mgr):
        with patch("src.api.routes.ws.validate_ws_token", return_value=True):
            client = TestClient(app)
            with client.websocket_connect("/api/v1/ws?token=valid") as ws:
                ws.send_text("ping")
                ws.close()
            mock_mgr.connect.assert_awaited_once()
            mock_mgr.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_ws_endpoint_invalid_token_rejects():
    with patch("src.api.routes.ws.validate_ws_token", return_value=False):
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws?token=invalid") as ws:
                pass
