import asyncio
import json
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json"}

_DEFAULT_TIMEOUT = 10.0


@dataclass
class WebhookResult:
    channel: str
    success: bool
    status_code: int | None = None
    error: str | None = None


def _build_payload(channel_type: str, title: str, text: str) -> dict:
    if channel_type == "dingtalk":
        return {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    if channel_type == "wechat":
        return {"msgtype": "markdown", "markdown": {"content": f"## {title}\n{text}"}}
    if channel_type == "feishu":
        return {"msg_type": "interactive", "card": {"header": {"title": {"tag": "plain_text", "content": title}}, "elements": [{"tag": "markdown", "content": text}]}}
    raise ValueError(f"Unsupported channel type: {channel_type}")


async def send_notification(channel_type: str, webhook_url: str, title: str, text: str) -> WebhookResult:
    try:
        payload = _build_payload(channel_type, title, text)
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(webhook_url, json=payload, headers=_HEADERS)
        if resp.is_success:
            return WebhookResult(channel=channel_type, success=True, status_code=resp.status_code)
        return WebhookResult(channel=channel_type, success=False, status_code=resp.status_code, error=resp.text[:200])
    except httpx.TimeoutException:
        return WebhookResult(channel=channel_type, success=False, error="timeout")
    except httpx.RequestError as e:
        return WebhookResult(channel=channel_type, success=False, error=str(e))
    except Exception as e:
        return WebhookResult(channel=channel_type, success=False, error=str(e))


def _load_channels() -> list[dict]:
    from src.api.routes.admin.notifications import _load
    return _load()


async def send_alert_to_all(event_type: str, camera_id: str, message: str, **extra) -> list[WebhookResult]:
    channels = _load_channels()
    results: list[WebhookResult] = []
    for ch in channels:
        if ch.get("enabled") and ch["config"].get("webhook_url"):
            title = f"[{event_type}] {camera_id}"
            r = await send_notification(ch["type"], ch["config"]["webhook_url"], title, message)
            if not r.success:
                logger.warning("Webhook send failed: %s -> %s (status=%s, err=%s)", ch["name"], ch["type"], r.status_code, r.error)
            results.append(r)
    return results


def _handle_alert_callback(payload_json: str) -> None:
    try:
        data = json.loads(payload_json)
        event_type = data.get("type", "unknown")
        camera_id = data.get("camera_id", "unknown")
        message = data.get("message", "")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_alert_to_all(event_type, camera_id, message))
        except RuntimeError:
            logger.warning("No running event loop, cannot send webhook alert")
    except json.JSONDecodeError:
        logger.warning("Invalid alert payload: %s", payload_json[:100])


def register_webhook_callbacks() -> None:
    from src.ingestion.stream_manager import register_alert_callback
    register_alert_callback(_handle_alert_callback)
    logger.info("Webhook alert callbacks registered")
