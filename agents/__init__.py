"""
agents/ — the Chief Officer analytical agents.

Phase 2 (this delivery): Chief Macro Officer, Chief Bond Strategist.
Every agent inherits from BaseAgent, which enforces the platform's hard rule:
no agent may produce a directional call using data that isn't
`Dataset.is_usable()`. See docs/ARCHITECTURE.md for the full pattern.

Remaining ten officers (Commodity, Equity, FX, Crypto, Sentiment, Technical,
Risk, Strategy, Learning, Execution) land in later phases using this same
BaseAgent pattern — no architecture change required.
"""

from .base_agent import BaseAgent
from .chief_macro_officer import ChiefMacroOfficer
from .chief_bond_strategist import ChiefBondStrategist

__all__ = ["BaseAgent", "ChiefMacroOfficer", "ChiefBondStrategist"]
