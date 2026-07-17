"""
Chief FX Analyst.

Phase 3 scope: CFTC COT speculative positioning trend for a given currency
future (EUR, JPY, GBP, etc. — one agent instance per market). Per the full
spec's FX coverage (central bank divergence, rate differentials, DXY,
capital flows, trade balances...), those slot into this same agent as
additional weighted components in a later phase, reusing the interest-rate
data the Chief Bond Strategist (Phase 2) already pulls from FRED for rate
differential calculations — no new architecture needed.
"""

from __future__ import annotations

from .positioning_agent_base import PositioningAgent


class ChiefFXAnalyst(PositioningAgent):
    department = "Chief FX Analyst"
