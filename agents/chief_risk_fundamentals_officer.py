"""
Chief Risk Fundamentals Officer.

Per the Institutional Fundamental Scoring Engine spec's "Risk Assessment"
section (Volatility, Correlation, Portfolio Risk, Drawdown Risk, Liquidity
Risk, Event Risk, Risk Score) — this agent covers the PER-ASSET slice of
that list: Volatility and Drawdown Risk, both genuinely computable from
free Yahoo Finance price history using the exact same tested pure-Python
math (agents/risk_calculations.py) the portfolio-level Chief Risk Officer
(Phase 6) already uses — no new calculation logic, no new connector.

HONEST SCOPE — why the rest of the spec's Risk Assessment list is NOT
duplicated here:
    - Correlation and Portfolio Risk are inherently PORTFOLIO-level
      concepts (they need multiple positions to correlate against) —
      already covered by agents/chief_risk_officer.py, which takes a
      Portfolio of positions, not a single asset. Rebuilding them here
      for one asset in isolation wouldn't mean anything.
    - Event Risk (news/calendar-driven) is covered by the separate
      Institutional Trade Decision Engine's agents/asset_risk_officer.py
      (EVENT_RISK_KEYWORDS), which was deliberately kept as its own
      feature per an earlier explicit scoping decision — not duplicated
      into the main pipeline here.
    - Liquidity Risk (bid-ask spreads, market depth) has no free,
      structured, live source this platform integrates — absent, not faked.

This agent is instantiated per-ticker (same pattern as
agents.chief_commodity_fundamentals_officer.ChiefCommodityFundamentalsOfficer),
reusing the SAME "PRICE_HISTORY_<TICKER>" DataIntegrityManager key
convention the portfolio-level Chief Risk Officer already uses — if both
are run for the same ticker, they share one cached fetch, not two.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel
from models.fundamental_factor import FundamentalFactor, factor_bias_from_score

from .base_agent import BaseAgent
from .fundamental_scoring_engine import score_category
from .risk_calculations import daily_returns, annualized_volatility, max_drawdown
from .risk_severity import worse_risk_level

CATEGORY = "Risk"
FACTOR_BASE_CONFIDENCE = 70.0

# Same thresholds as agents/chief_risk_officer.py, for consistency across
# the platform's two risk-scoring paths (portfolio-level and per-asset).
VOLATILITY_ELEVATED_PCT = 25.0
VOLATILITY_HIGH_PCT = 40.0
DRAWDOWN_ELEVATED_PCT = -20.0
DRAWDOWN_HIGH_PCT = -35.0


def _score_volatility(vol_pct: float) -> float:
    """Lower volatility -> favorable (bullish-leaning) score; higher -> unfavorable."""
    if vol_pct >= VOLATILITY_HIGH_PCT:
        return -60.0
    if vol_pct >= VOLATILITY_ELEVATED_PCT:
        return -30.0
    if vol_pct < 15.0:
        return 20.0
    return 0.0


def _score_drawdown(dd_pct: float) -> float:
    """A shallower (less negative) drawdown from peak -> favorable score; a deep one -> unfavorable."""
    if dd_pct <= DRAWDOWN_HIGH_PCT:
        return -40.0
    if dd_pct <= DRAWDOWN_ELEVATED_PCT:
        return -20.0
    if dd_pct > -10.0:
        return 10.0
    return 0.0


class ChiefRiskFundamentalsOfficer(BaseAgent):
    department = "Chief Risk Fundamentals Officer"

    def __init__(self, manager, ticker: str, min_quality: float = 60.0):
        super().__init__(manager, min_quality)
        self.ticker = ticker
        self.price_key = f"PRICE_HISTORY_{ticker}"

    def required_dataset_keys(self) -> List[str]:
        return [self.price_key]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        factors: List[FundamentalFactor] = []
        data_gaps: List[str] = []
        risk_level = RiskLevel.MODERATE

        ds = usable.get(self.price_key)
        if ds is not None:
            history = ds.payload.get("history", [])
            closes_oldest_first = [row["close"] for row in reversed(history) if "close" in row]

            if len(closes_oldest_first) >= 2:
                returns = daily_returns(closes_oldest_first)
                vol = annualized_volatility(returns)
                dd = max_drawdown(closes_oldest_first)

                if vol is not None:
                    vol_score = _score_volatility(vol)
                    factors.append(FundamentalFactor(
                        name="Annualized Volatility",
                        category=CATEGORY,
                        current_value=round(vol, 2),
                        score=vol_score,
                        bias=factor_bias_from_score(vol_score),
                        importance_weight=6.0,
                        confidence=FACTOR_BASE_CONFIDENCE,
                        source=ds.source,
                        last_updated=ds.provider_timestamp or ds.time_collected,
                        notes=[f"{vol:.1f}% annualized, from {len(closes_oldest_first)} daily closes"],
                    ))
                    if vol >= VOLATILITY_HIGH_PCT:
                        risk_level = worse_risk_level(risk_level, RiskLevel.HIGH)
                    elif vol >= VOLATILITY_ELEVATED_PCT:
                        risk_level = worse_risk_level(risk_level, RiskLevel.ELEVATED)

                if dd is not None:
                    dd_score = _score_drawdown(dd)
                    factors.append(FundamentalFactor(
                        name="Maximum Drawdown",
                        category=CATEGORY,
                        current_value=round(dd, 2),
                        score=dd_score,
                        bias=factor_bias_from_score(dd_score),
                        importance_weight=5.0,
                        confidence=FACTOR_BASE_CONFIDENCE,
                        source=ds.source,
                        last_updated=ds.provider_timestamp or ds.time_collected,
                        notes=[f"{dd:.1f}% peak-to-trough over the fetched window"],
                    ))
                    if dd <= DRAWDOWN_HIGH_PCT:
                        risk_level = worse_risk_level(risk_level, RiskLevel.HIGH)
                    elif dd <= DRAWDOWN_ELEVATED_PCT:
                        risk_level = worse_risk_level(risk_level, RiskLevel.ELEVATED)
            else:
                data_gaps.append(f"{self.price_key} (insufficient history to compute risk metrics)")

        category_result = score_category(CATEGORY, factors)

        evidence = [f"{f.name}: {f.notes[0]}" for f in factors]
        risks = [f"{f.name} is elevated ({f.notes[0]})" for f in factors if f.bias.value == "bearish"]
        catalysts = [f"{f.name} is favorable ({f.notes[0]})" for f in factors if f.bias.value == "bullish"]

        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=category_result.bias,
            bias_score=category_result.category_score,
            confidence=category_result.category_confidence,
            risk_level=risk_level if factors else RiskLevel.HIGH,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=data_gaps,
            factor_breakdown=factors,
        )
