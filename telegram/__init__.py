"""
telegram/ — Chief Execution Officer alerting. Built in Phase 9.

telegram_alerter.py: TelegramAlerter, a free Bot API wrapper. See
agents/chief_execution_officer.py for the gating logic that decides
WHETHER to call it — this module only knows how to send, never when.
"""

from .telegram_alerter import TelegramAlerter, TelegramError

__all__ = ["TelegramAlerter", "TelegramError"]
