"""
agents/ — the Chief Officer analytical agents. All 12 are now built.

Phase 2: Chief Macro Officer, Chief Bond Strategist.
Phase 3: Chief Commodity Analyst, Chief FX Analyst.
Phase 4: Chief Equity Analyst, Chief Cryptocurrency Analyst.
Phase 5: Chief Sentiment Officer, Chief Technical Officer.
Phase 6: Chief Risk Officer.
Phase 7: Chief Strategy Officer.
Phase 8: Chief Learning Officer.
Phase 9 (this delivery): Chief Execution Officer.

Four architectural shapes exist:
- BaseAgent: single-asset agents that fetch data via DataIntegrityManager
  (Phases 2-5).
- PortfolioAgent: agents that analyze a whole Portfolio of positions,
  same data-integrity contract, keyed by symbol (Phase 6).
- ChiefStrategyOfficer / ChiefExecutionOfficer: fetch NO data themselves —
  pure synthesis/gating over reports other agents already produced
  (Phases 7 & 9).
- ChiefLearningOfficer: not an analyst at all — a persistence sink and
  performance-analytics query engine (Phase 8).

See docs/ARCHITECTURE.md and the per-phase docs/ARCHITECTURE_PHASE*.md
files for the full patterns.
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
from .portfolio_agent_base import PortfolioAgent
from .chief_risk_officer import ChiefRiskOfficer
from .chief_strategy_officer import ChiefStrategyOfficer
from .chief_learning_officer import ChiefLearningOfficer
from .chief_execution_officer import ChiefExecutionOfficer

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
    "PortfolioAgent",
    "ChiefRiskOfficer",
    "ChiefStrategyOfficer",
    "ChiefLearningOfficer",
    "ChiefExecutionOfficer",
]
