"""
agents/ — the Chief Officer analytical agents.

Phase 2: Chief Macro Officer, Chief Bond Strategist.
Phase 3: Chief Commodity Analyst, Chief FX Analyst.
Phase 4: Chief Equity Analyst, Chief Cryptocurrency Analyst.
Phase 5 (this delivery): Chief Sentiment Officer, Chief Technical Officer.

Every agent inherits from BaseAgent, which enforces the platform's hard rule:
no agent may produce a directional call using data that isn't
`Dataset.is_usable()`. See docs/ARCHITECTURE.md and the per-phase
docs/ARCHITECTURE_PHASE*.md files for the full patterns.

Remaining four officers (Risk, Strategy, Learning, Execution) land in later
phases using these same patterns — no architecture change required.
"""

from .base_agent import BaseAgent
from .chief_macro_officer import ChiefMacroOfficer
from .chief_bond_strategist import ChiefBondStrategist
from .positioning_agent_base import PositioningAgent
from .chief_commodity_analyst import ChiefCommodityAnalyst
from .chief_fx_analyst import ChiefFXAnalyst
from .chief_equity_analyst import ChiefEquityAnalyst
from .chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst
from .chief_sentiment_officer import ChiefSentimentOfficer
from .chief_technical_officer import ChiefTechnicalOfficer

__all__ = [
    "BaseAgent",
    "ChiefMacroOfficer",
    "ChiefBondStrategist",
    "PositioningAgent",
    "ChiefCommodityAnalyst",
    "ChiefFXAnalyst",
    "ChiefEquityAnalyst",
    "ChiefCryptocurrencyAnalyst",
    "ChiefSentimentOfficer",
    "ChiefTechnicalOfficer",
]
