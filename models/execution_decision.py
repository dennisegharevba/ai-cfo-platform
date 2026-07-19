"""
ExecutionDecision: the Chief Execution Officer's verdict on whether a
synthesized StrategyReport clears the bar to alert on.

Kept as its own small model (not bolted onto StrategyReport) because it's
about a DIFFERENT question — not "what does the platform think," but
"should a human be pinged about it right now" — and because it's useful to
be able to record every decision (including blocked ones) for audit, not
just the ones that resulted in a sent alert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class ExecutionDecision:
    asset_or_theme: str
    should_alert: bool
    blocking_reasons: List[str] = field(default_factory=list)  # empty if should_alert is True
    alert_sent: bool = False        # set True only after a real send succeeds
    send_error: str = ""            # populated if should_alert was True but sending failed
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
