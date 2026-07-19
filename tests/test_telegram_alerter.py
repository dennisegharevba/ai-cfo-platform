from unittest.mock import patch, MagicMock

import pytest

from telegram.telegram_alerter import TelegramAlerter, TelegramError


def _mock_response(payload, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_send_message_success():
    with patch("telegram.telegram_alerter.requests.post",
               return_value=_mock_response({"ok": True, "result": {"message_id": 123}})) as mock_post:
        alerter = TelegramAlerter(bot_token="FAKE_TOKEN", chat_id="12345")
        result = alerter.send_message("Hello")
    assert result["ok"] is True
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["chat_id"] == "12345"
    assert kwargs["json"]["text"] == "Hello"


def test_missing_credentials_raises_before_any_request():
    alerter = TelegramAlerter(bot_token="", chat_id="")
    with pytest.raises(TelegramError):
        alerter.send_message("Hello")


def test_api_rejection_raises_telegram_error():
    with patch("telegram.telegram_alerter.requests.post",
               return_value=_mock_response({"ok": False, "description": "chat not found"})):
        alerter = TelegramAlerter(bot_token="FAKE_TOKEN", chat_id="BAD_CHAT")
        with pytest.raises(TelegramError):
            alerter.send_message("Hello")


def test_network_failure_raises_telegram_error():
    import requests as requests_module
    with patch("telegram.telegram_alerter.requests.post", side_effect=requests_module.ConnectionError("boom")):
        alerter = TelegramAlerter(bot_token="FAKE_TOKEN", chat_id="12345")
        with pytest.raises(TelegramError):
            alerter.send_message("Hello")
