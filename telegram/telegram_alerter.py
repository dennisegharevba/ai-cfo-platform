"""
Telegram alerter — free Bot API, no cost beyond creating a bot via
@BotFather and getting your chat ID.

Deliberately NOT a core.DataSource subclass: DataSource is for fetching
data into the platform; this is an output sink that sends data OUT. Mixing
the two into one abstraction would blur "things the integrity manager
gates" with "things that happen after a decision has already been made."
"""

from __future__ import annotations

from typing import Any, Dict

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    """Raised when a Telegram API call fails (network, auth, bad chat id, etc.)."""


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str, timeout: int = 10):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    def send_message(self, text: str, parse_mode: str = "Markdown") -> Dict[str, Any]:
        if not self.bot_token or not self.chat_id:
            raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set")

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TelegramError(f"Telegram sendMessage request failed: {exc}") from exc

        # Telegram's Bot API returns a JSON body with a real, actionable
        # "description" field EVEN on 4xx/5xx HTTP status codes (e.g.
        # "Bad Request: chat not found" vs "Bad Request: can't parse
        # entities: character '-' is reserved and must be escaped").
        # Reading the body BEFORE checking resp.ok — rather than calling
        # resp.raise_for_status() immediately, which discards the body —
        # is what makes that real description available. Found via live
        # testing: without this fix, every HTTP-level failure showed only
        # a bare "400 Client Error: Bad Request for url: ..." with the
        # actual reason completely invisible, making it impossible to
        # tell a bad chat_id apart from a message-formatting problem.
        try:
            data = resp.json()
        except ValueError:
            data = None

        if not resp.ok:
            if data and "description" in data:
                raise TelegramError(f"Telegram API rejected the message: {data['description']}")
            raise TelegramError(
                f"Telegram sendMessage request failed: {resp.status_code} {resp.reason} for url: {resp.url}"
            )

        if data is None:
            raise TelegramError("Telegram returned invalid JSON")

        if not data.get("ok", False):
            raise TelegramError(f"Telegram API rejected the message: {data.get('description', 'unknown error')}")

        return data
