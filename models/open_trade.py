"""
OpenTrade: records the state of the world AT ENTRY for a trade the user has
actually taken, so agents/trade_lifecycle_officer.py has something concrete
to check for invalidation against later — per spec section 4, lifecycle
management must NOT just watch the Overall Score fall, it must check
whether the specific conditions that justified entry are still true.

This platform never places trades itself (see database/schema.py's note on
`outcomes` being recorded from observed market data, not from any order the
platform placed) — OpenTrade is a user-declared record ("I took this trade")
that the platform then monitors, not something the platform originates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class TradeDirection(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class OpenTrade:
    id: Optional[int]  # None until persisted (ReportStore assigns it)
    asset_or_theme: str
    direction: TradeDirection

    # --- Snapshot at entry: what agents/trade_lifecycle_officer.py checks
    # current conditions against, per spec section 4's six questions ---
    entry_technical_bias_score: float      # Chief Technical Officer's bias_score at entry
    entry_fundamental_bias_score: float    # blended fundamental bias_score at entry
    entry_risk_score: float                # Risk Score at entry
    entry_market_structure_note: str       # e.g. "Higher-high confirmed above 2050"
    stop_loss_level: Optional[float] = None
    entry_price: Optional[float] = None

    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    close_reason: str = ""

    def is_open(self) -> bool:
        return self.closed_at is None
