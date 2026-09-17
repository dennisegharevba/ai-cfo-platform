"""
agents/ — the Chief Officer analytical agents.

Phase 2: Chief Macro Officer, Chief Bond Strategist.
Phase 3: Chief Commodity Analyst, Chief FX Analyst.
Phase 4: Chief Equity Analyst, Chief Cryptocurrency Analyst.
Phase 5: Chief Sentiment Officer, (Chief Technical Officer — later removed
from the main scoring pipeline per user request; see
docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md. The platform now scores
purely on fundamentals + macro + global news/sentiment. Its own separate
momentum/technical logic inside the Trade Decision Engine, which is a
different feature with a different purpose, was deliberately kept as-is.)
Phase 6: Chief Risk Officer.
Phase 7: Chief Strategy Officer.
Phase 8: Chief Learning Officer.
Phase 9: Chief Execution Officer.

Four architectural shapes exist:
- BaseAgent: single-asset agents that fetch data via DataIntegrityManager.
- PortfolioAgent: agents that analyze a whole Portfolio of positions,
  same data-integrity contract, keyed by symbol (Chief Risk Officer).
- ChiefStrategyOfficer / ChiefExecutionOfficer: fetch NO data themselves —
  pure synthesis/gating over reports other agents already produced.
- ChiefLearningOfficer: not an analyst at all — a persistence sink and
  performance-analytics query engine.

See docs/ARCHITECTURE.md and the per-phase docs/ARCHITECTURE_PHASE*.md
files for the full patterns.
"""

from .base_agent import BaseAgent
from .chief_macro_officer import ChiefMacroOfficer
from .chief_bond_strategist import ChiefBondStrategist
from .positioning_agent_base import PositioningAgent
from .chief_commodity_analyst import ChiefCommodityAnalyst
from .chief_commodity_fundamentals_officer import ChiefCommodityFundamentalsOfficer
from .chief_fx_analyst import ChiefFXAnalyst
from .chief_equity_analyst import ChiefEquityAnalyst
from .chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst
from .chief_sentiment_officer import ChiefSentimentOfficer
from .portfolio_agent_base import PortfolioAgent
from .chief_risk_officer import ChiefRiskOfficer
from .chief_risk_fundamentals_officer import ChiefRiskFundamentalsOfficer
from .chief_strategy_officer import ChiefStrategyOfficer
from .chief_seasonality_officer import ChiefSeasonalityOfficer
from .chief_learning_officer import ChiefLearningOfficer
from .chief_execution_officer import ChiefExecutionOfficer

__all__ = [
    "BaseAgent",
    "ChiefMacroOfficer",
    "ChiefBondStrategist",
    "PositioningAgent",
    "ChiefCommodityAnalyst",
    "ChiefCommodityFundamentalsOfficer",
    "ChiefFXAnalyst",
    "ChiefEquityAnalyst",
    "ChiefCryptocurrencyAnalyst",
    "ChiefSentimentOfficer",
    "PortfolioAgent",
    "ChiefRiskOfficer",
    "ChiefRiskFundamentalsOfficer",
    "ChiefStrategyOfficer",
    "ChiefSeasonalityOfficer",
    "ChiefLearningOfficer",
    "ChiefExecutionOfficer",
]
