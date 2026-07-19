import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

from src.monitoring.structured_log import log_with_fields

logger = logging.getLogger(__name__)

_EXCLUDE_PATHS = {"/metrics", "/api/v1/health"}


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _EXCLUDE_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start = time.monotonic()
        status = [200]

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                status[0] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            elapsed = (time.monotonic() - start) * 1000
            fields = {
                "method": method,
                "path": path,
                "status": status[0],
                "duration_ms": round(elapsed, 1),
                "component": "request_logger",
            }
            if elapsed > 1000:
                log_with_fields(logger, logging.WARNING, f"SLOW {method} {path} -> {status[0]} ({elapsed:.0f}ms)", **fields)
            else:
                log_with_fields(logger, logging.INFO, f"{method} {path} -> {status[0]} ({elapsed:.0f}ms)", **fields)
