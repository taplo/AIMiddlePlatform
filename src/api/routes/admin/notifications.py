import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/notifications", tags=["admin-notifications"])

CHANNELS_FILE: str | None = None

try:
    from pathlib import Path
    CHANNELS_FILE = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "config" / "notification_channels.json")
except Exception:
    CHANNELS_FILE = "config/notification_channels.json"

DEFAULT_CHANNELS = [
    {"name": "DingTalk", "type": "dingtalk", "enabled": False, "config": {"webhook_url": ""}},
    {"name": "WeChat Work", "type": "wechat", "enabled": False, "config": {"webhook_url": ""}},
    {"name": "Feishu", "type": "feishu", "enabled": False, "config": {"webhook_url": ""}},
]


def _load() -> list[dict]:
    try:
        with open(CHANNELS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [dict(c) for c in DEFAULT_CHANNELS]


def _save(channels: list[dict]) -> None:
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


class ChannelUpdate(BaseModel):
    enabled: bool
    config: dict


@router.get("")
async def list_channels() -> list[dict]:
    return _load()


@router.put("/{channel_name}")
async def update_channel(channel_name: str, body: ChannelUpdate) -> list[dict]:
    channels = _load()
    for c in channels:
        if c["name"] == channel_name:
            c["enabled"] = body.enabled
            c["config"].update(body.config)
            _save(channels)
            return channels
    raise HTTPException(404, f"Channel '{channel_name}' not found")
