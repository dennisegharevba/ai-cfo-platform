"""
Chief Commodity Analyst.

Phase 3 scope: CFTC COT speculative positioning trend for a given commodity
(gold, silver, crude oil, corn, etc. — one agent instance per market). Per
the full spec's commodity coverage (USDA, WASDE, EIA, weather, shipping,
seasonality...), this agent's `_build_report` is the natural place to add
those as additional weighted components in a later phase — the
PositioningAgent base class and COT-driven scoring stay unchanged.
"""

from __future__ import annotations

from .positioning_agent_base import PositioningAgent


class ChiefCommodityAnalyst(PositioningAgent):
    department = "Chief Commodity Analyst"
