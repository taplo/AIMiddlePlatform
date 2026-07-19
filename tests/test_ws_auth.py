from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from src.ws.auth import validate_ws_token


def test_valid_jwt_token_returns_true():
    with patch("src.ws.auth.get_current_user", return_value="admin"):
        result = validate_ws_token("valid_jwt_token")
    assert result is True


def test_invalid_jwt_but_valid_api_key_returns_true():
    with patch("src.ws.auth.get_current_user", side_effect=HTTPException(401)):
        with patch("src.ws.auth.get_api_key_store") as mock_store_fn:
            mock_store = MagicMock()
            mock_store.validate.return_value = {"name": "test"}
            mock_store_fn.return_value = mock_store
            result = validate_ws_token("valid_api_key_abc123")
    assert result is True


def test_invalid_jwt_and_no_api_key_returns_false():
    with patch("src.ws.auth.get_current_user", side_effect=HTTPException(401)):
        with patch("src.ws.auth.get_api_key_store") as mock_store_fn:
            mock_store = MagicMock()
            mock_store.validate.return_value = None
            mock_store_fn.return_value = mock_store
            result = validate_ws_token("invalid_token")
    assert result is False
