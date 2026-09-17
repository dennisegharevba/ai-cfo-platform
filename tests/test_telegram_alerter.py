from unittest.mock import patch, MagicMock

import pytest

from telegram.telegram_alerter import TelegramAlerter, TelegramError


def _mock_response(payload, status_ok=True, status_code=200, reason="OK", url="https://api.telegram.org/fake"):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    resp.ok = status_ok
    resp.status_code = status_code
    resp.reason = reason
    resp.url = url
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


# --- HTTP-level error responses (4xx/5xx) that still carry a real JSON description ---

def test_http_400_with_chat_not_found_description_surfaces_the_real_reason():
    """
    Regression test for a real gap found via live testing: Telegram
    returns a genuine 400 Bad Request for an invalid/mismatched chat_id,
    but the response body still contains a real, actionable
    "description" field ("Bad Request: chat not found"). The original
    code called raise_for_status() before ever reading that body,
    discarding it — every HTTP-level failure showed only a bare
    "400 Client Error: Bad Request for url: ..." with the ACTUAL reason
    invisible, making it impossible to tell a bad chat_id apart from any
    other kind of failure.
    """
    payload = {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
    with patch("telegram.telegram_alerter.requests.post",
               return_value=_mock_response(payload, status_ok=False, status_code=400, reason="Bad Request")):
        alerter = TelegramAlerter(bot_token="FAKE_TOKEN", chat_id="WRONG_ID")
        with pytest.raises(TelegramError, match="chat not found"):
            alerter.send_message("Hello")


def test_http_400_with_markdown_parse_error_surfaces_the_real_reason():
    """The other realistic 400 cause this fix needed to distinguish from
    a bad chat_id: a message containing characters Telegram's Markdown
    parser can't handle."""
    payload = {"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities: Character '-' is reserved and must be escaped"}
    with patch("telegram.telegram_alerter.requests.post",
               return_value=_mock_response(payload, status_ok=False, status_code=400, reason="Bad Request")):
        alerter = TelegramAlerter(bot_token="FAKE_TOKEN", chat_id="12345")
        with pytest.raises(TelegramError, match="can't parse entities"):
            alerter.send_message("Hello *world")


def test_http_error_with_no_json_body_falls_back_to_status_line():
    """If Telegram (or a proxy in front of it) returns an HTTP error with
    no parseable JSON body at all, the error should still be clear —
    just without a Telegram-specific description to add."""
    resp = MagicMock()
    resp.json.side_effect = ValueError("not JSON")
    resp.ok = False
    resp.status_code = 502
    resp.reason = "Bad Gateway"
    resp.url = "https://api.telegram.org/fake"
    with patch("telegram.telegram_alerter.requests.post", return_value=resp):
        alerter = TelegramAlerter(bot_token="FAKE_TOKEN", chat_id="12345")
        with pytest.raises(TelegramError, match="502"):
            alerter.send_message("Hello")
