import logging
from fastapi import HTTPException
from src.api.routes.admin.auth import get_current_user
from src.core.security import get_api_key_store

logger = logging.getLogger(__name__)


def validate_ws_token(token: str) -> bool:
    try:
        get_current_user(token)
        return True
    except HTTPException:
        pass
    store = get_api_key_store()
    if store.validate(token):
        return True
    logger.warning("WebSocket connection rejected: invalid token")
    return False
