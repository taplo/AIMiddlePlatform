import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

from src.monitoring.structured_log import log_with_fields

logger = logging.getLogger(__name__)

_EXCLUDE_PATHS = {"/metrics", "/api/v1/health"}


def _get_header(scope: Scope, name: bytes) -> str:
    headers = scope.get("headers", [])
    for k, v in headers:
        if k.lower() == name:
            return v.decode("utf-8", errors="replace")
    return ""


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
            client = scope.get("client")
            if client:
                fields["client_ip"] = client[0]
            user_agent = _get_header(scope, b"user-agent")
            if user_agent:
                fields["user_agent"] = user_agent
            try:
                from opentelemetry import trace as otel_trace
                span = otel_trace.get_current_span()
                span_ctx = span.get_span_context()
                if span_ctx.trace_id != 0:
                    fields["trace_id"] = hex(span_ctx.trace_id)
            except Exception:
                pass
            if elapsed > 1000:
                log_with_fields(logger, logging.WARNING, f"SLOW {method} {path} -> {status[0]} ({elapsed:.0f}ms)", **fields)
            else:
                log_with_fields(logger, logging.INFO, f"{method} {path} -> {status[0]} ({elapsed:.0f}ms)", **fields)
