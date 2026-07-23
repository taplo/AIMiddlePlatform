import pytest

from src.notification.sender import (
    WebhookResult,
    _build_payload,
    send_notification,
    send_alert_to_all,
)


def test_build_payload_dingtalk():
    payload = _build_payload("dingtalk", "Alert", "test message")
    assert payload["msgtype"] == "markdown"
    assert payload["markdown"]["title"] == "Alert"
    assert payload["markdown"]["text"] == "test message"


def test_build_payload_wechat():
    payload = _build_payload("wechat", "Alert", "test message")
    assert payload["msgtype"] == "markdown"
    assert "Alert" in payload["markdown"]["content"]


def test_build_payload_feishu():
    payload = _build_payload("feishu", "Alert", "test message")
    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "Alert"


def test_build_payload_unsupported():
    with pytest.raises(ValueError, match="Unsupported"):
        _build_payload("unknown", "t", "m")


@pytest.mark.asyncio
async def test_send_notification_timeout():
    result = await send_notification("dingtalk", "http://localhost:1", "Test", "msg")
    assert isinstance(result, WebhookResult)
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_send_notification_http_error():
    result = await send_notification("dingtalk", "http://0.0.0.0:1", "Test", "msg")
    assert result.success is False


@pytest.mark.asyncio
async def test_send_alert_to_all_no_channels(monkeypatch):
    monkeypatch.setattr("src.notification.sender._load_channels", lambda: [])
    results = await send_alert_to_all("test_event", "cam-01", "test msg")
    assert results == []
