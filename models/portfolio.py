"""
Portfolio / Position: the input shape for the Chief Risk Officer.

Every prior agent (Phases 2-5) analyzes ONE asset or theme at a time. The
Chief Risk Officer is architecturally different — its whole job is to look
ACROSS a set of held positions (concentration, correlation, portfolio-level
VaR), so its input is a Portfolio, not a single ticker/theme string. See
docs/ARCHITECTURE_PHASE6.md for why this needed a new base class
(PortfolioAgent) rather than reusing BaseAgent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Position:
    symbol: str          # ticker the platform can fetch price history for, e.g. "AAPL", "SPY"
    quantity: float       # shares/contracts/units held (can be negative for a short)
    asset_class: str = "equity"  # informational only in Phase 6; not used in risk math yet


@dataclass
class Portfolio:
    name: str
    positions: List[Position] = field(default_factory=list)

    def symbols(self) -> List[str]:
        return [p.symbol for p in self.positions]
