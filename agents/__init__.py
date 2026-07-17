"""
agents/ — the Chief Officer analytical agents.

Phase 2: Chief Macro Officer, Chief Bond Strategist.
Phase 3 (this delivery): Chief Commodity Analyst, Chief FX Analyst.

Every agent inherits from BaseAgent, which enforces the platform's hard rule:
no agent may produce a directional call using data that isn't
`Dataset.is_usable()`. See docs/ARCHITECTURE.md and
docs/ARCHITECTURE_PHASE3.md for the full patterns.

Remaining eight officers (Equity, Crypto, Sentiment, Technical, Risk,
Strategy, Learning, Execution) land in later phases using these same
BaseAgent / PositioningAgent patterns — no architecture change required.
"""

from .base_agent import BaseAgent
from .chief_macro_officer import ChiefMacroOfficer
from .chief_bond_strategist import ChiefBondStrategist
from .positioning_agent_base import PositioningAgent
from .chief_commodity_analyst import ChiefCommodityAnalyst
from .chief_fx_analyst import ChiefFXAnalyst

__all__ = [
    "BaseAgent",
    "ChiefMacroOfficer",
    "ChiefBondStrategist",
    "PositioningAgent",
    "ChiefCommodityAnalyst",
    "ChiefFXAnalyst",
]
