"""
agents/ — the Chief Officer analytical agents.

Phase 2: Chief Macro Officer, Chief Bond Strategist.
Phase 3: Chief Commodity Analyst, Chief FX Analyst.
Phase 4: Chief Equity Analyst, Chief Cryptocurrency Analyst.
Phase 5: Chief Sentiment Officer, Chief Technical Officer.
Phase 6: Chief Risk Officer.
Phase 7: Chief Strategy Officer.
Phase 8 (this delivery): Chief Learning Officer.

Four architectural shapes exist:
- BaseAgent: single-asset agents that fetch data via DataIntegrityManager
  (Phases 2-5).
- PortfolioAgent: agents that analyze a whole Portfolio of positions,
  same data-integrity contract, keyed by symbol (Phase 6).
- ChiefStrategyOfficer: fetches NO data itself — pure synthesis over
  AgentReports other agents already produced (Phase 7).
- ChiefLearningOfficer: not an analyst at all — a persistence sink and
  performance-analytics query engine over everything that's been recorded
  (Phase 8).

See docs/ARCHITECTURE.md and the per-phase docs/ARCHITECTURE_PHASE*.md
files for the full patterns.

One officer remains: Chief Execution Officer (Phase 9).
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
]
