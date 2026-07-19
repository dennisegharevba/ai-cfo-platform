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
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise TelegramError(f"Telegram sendMessage request failed: {exc}") from exc
        except ValueError as exc:
            raise TelegramError(f"Telegram returned invalid JSON: {exc}") from exc

        if not data.get("ok", False):
            raise TelegramError(f"Telegram API rejected the message: {data.get('description', 'unknown error')}")

        return data
