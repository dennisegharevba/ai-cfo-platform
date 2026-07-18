"""
Chief Risk Officer.

Phase 6 scope: given a Portfolio of positions, using each position's daily
close history (reusing the Phase 5 YahooHistoryConnector — this agent adds
no new connector, just a new way of consuming the existing one across many
symbols at once):

    - Concentration: largest position's share of total market value
    - Portfolio volatility: annualized, from value-weighted daily returns
    - Historical VaR (95%): from the same weighted return series
    - Max drawdown: from the reconstructed portfolio value index
    - Average pairwise correlation: a "this portfolio isn't as diversified
      as it looks" check

Unlike every other Chief Officer, this agent does NOT take a directional
view — per the spec, the Risk desk's job is to assess how risky the
portfolio is, not whether it's headed up or down. Bias/bias_score are
always neutral/0.0 here; `risk_level` and the evidence/risks lists carry
the actual assessment. See docs/ARCHITECTURE_PHASE6.md for the reasoning.

Known Phase 6 simplification (documented, not hidden): weighted portfolio
returns are combined by aligning each symbol's trailing N returns by
INDEX, not by calendar date. This is fine when all positions trade on the
same calendar (e.g. all US equities) but would be wrong to mix with assets
on a different trading calendar (e.g. crypto, which trades every day,
alongside equities, which don't). A later phase should align by date.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.dataset import Dataset
from models.portfolio import Portfolio
from models.report import AgentReport, Bias, RiskLevel

from .portfolio_agent_base import PortfolioAgent
from .risk_calculations import (
    daily_returns, annualized_volatility, historical_var, max_drawdown, pearson_correlation,
)

CONCENTRATION_ELEVATED_PCT = 40.0
CONCENTRATION_HIGH_PCT = 60.0
VOLATILITY_ELEVATED_PCT = 25.0
VOLATILITY_HIGH_PCT = 40.0
VAR95_ELEVATED_PCT = 3.0
VAR95_HIGH_PCT = 5.0
DRAWDOWN_ELEVATED_PCT = -20.0
DRAWDOWN_HIGH_PCT = -35.0
CORRELATION_ELEVATED = 0.7

_SEVERITY_ORDER = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.ELEVATED, RiskLevel.HIGH]


def _worse(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _SEVERITY_ORDER.index(a) >= _SEVERITY_ORDER.index(b) else b


def _closes_oldest_first(history: List[dict]) -> List[float]:
    values = []
    for row in reversed(history):
        try:
            values.append(float(row["close"]))
        except (KeyError, TypeError, ValueError):
            continue
    return values


class ChiefRiskOfficer(PortfolioAgent):
    department = "Chief Risk Officer"

    def __init__(self, manager, price_key_prefix: str = "PRICE_HISTORY_", min_quality: float = 60.0):
        """
        price_key_prefix: this agent looks up each position's price history
        under f"{price_key_prefix}{symbol}" — matching the convention used
        in scripts/demo_sentiment_technical_agents.py
        (e.g. "PRICE_HISTORY_SPY").
        """
        super().__init__(manager, min_quality)
        self.price_key_prefix = price_key_prefix

    def price_history_key_for(self, symbol: str) -> str:
        return f"{self.price_key_prefix}{symbol}"

    def _build_report(self, usable_by_symbol: Dict[str, Dataset], portfolio: Portfolio) -> AgentReport:
        evidence: List[str] = []
        risks: List[str] = []
        catalysts: List[str] = []
        risk_level = RiskLevel.MODERATE

        included_positions = [p for p in portfolio.positions if p.symbol in usable_by_symbol]

        if not included_positions:
            return AgentReport(
                department=self.department,
                asset_or_theme=portfolio.name,
                bias=Bias.NEUTRAL,
                bias_score=0.0,
                confidence=0.0,
                risk_level=RiskLevel.HIGH,
                evidence=[],
                risks=["No usable price data for any position — risk cannot be assessed"],
                catalysts=[],
                data_gaps=[],
            )

        # --- Market values & concentration ---
        market_values = {}
        for p in included_positions:
            latest_close = usable_by_symbol[p.symbol].payload.get("latest_close")
            if latest_close is not None:
                market_values[p.symbol] = abs(p.quantity) * float(latest_close)

        total_value = sum(market_values.values())
        weights = {sym: (mv / total_value if total_value else 0.0) for sym, mv in market_values.items()}

        if weights:
            largest_symbol = max(weights, key=weights.get)
            largest_weight_pct = weights[largest_symbol] * 100
            evidence.append(
                f"Largest position ({largest_symbol}) is {largest_weight_pct:.1f}% of portfolio market value"
            )
            if largest_weight_pct >= CONCENTRATION_HIGH_PCT:
                risk_level = _worse(risk_level, RiskLevel.HIGH)
                risks.append(f"Portfolio is highly concentrated in {largest_symbol} ({largest_weight_pct:.1f}%)")
            elif largest_weight_pct >= CONCENTRATION_ELEVATED_PCT:
                risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                risks.append(f"Portfolio has elevated concentration in {largest_symbol} ({largest_weight_pct:.1f}%)")
            elif largest_weight_pct < 30.0 and len(weights) >= 3:
                catalysts.append("No single position dominates the portfolio's market value")

        # --- Per-symbol returns ---
        returns_by_symbol: Dict[str, List[float]] = {}
        for p in included_positions:
            closes = _closes_oldest_first(usable_by_symbol[p.symbol].payload.get("history", []))
            rets = daily_returns(closes)
            if rets:
                returns_by_symbol[p.symbol] = rets

        # --- Weighted portfolio returns (documented index-alignment simplification) ---
        portfolio_returns: Optional[List[float]] = None
        if returns_by_symbol:
            min_len = min(len(r) for r in returns_by_symbol.values())
            if min_len > 0:
                portfolio_returns = []
                for i in range(min_len):
                    day_return = 0.0
                    for sym, rets in returns_by_symbol.items():
                        day_return += weights.get(sym, 0.0) * rets[-min_len + i]
                    portfolio_returns.append(day_return)

        if portfolio_returns:
            vol = annualized_volatility(portfolio_returns)
            if vol is not None:
                evidence.append(f"Portfolio annualized volatility is {vol:.1f}%")
                if vol >= VOLATILITY_HIGH_PCT:
                    risk_level = _worse(risk_level, RiskLevel.HIGH)
                    risks.append(f"Portfolio volatility ({vol:.1f}%) is very high")
                elif vol >= VOLATILITY_ELEVATED_PCT:
                    risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                    risks.append(f"Portfolio volatility ({vol:.1f}%) is elevated")

            var95 = historical_var(portfolio_returns, confidence=0.95)
            if var95 is not None:
                evidence.append(f"Historical 1-day 95% VaR is {var95:.2f}%")
                if var95 >= VAR95_HIGH_PCT:
                    risk_level = _worse(risk_level, RiskLevel.HIGH)
                    risks.append(f"1-day 95% VaR ({var95:.2f}%) implies a large potential daily loss")
                elif var95 >= VAR95_ELEVATED_PCT:
                    risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                    risks.append(f"1-day 95% VaR ({var95:.2f}%) is elevated")

            # Reconstruct a portfolio value index from weighted returns to measure drawdown.
            index_values = [1.0]
            for r in portfolio_returns:
                index_values.append(index_values[-1] * (1 + r))
            dd = max_drawdown(index_values)
            if dd is not None:
                evidence.append(f"Portfolio max drawdown over the sampled window is {dd:.1f}%")
                if dd <= DRAWDOWN_HIGH_PCT:
                    risk_level = _worse(risk_level, RiskLevel.HIGH)
                    risks.append(f"Max drawdown ({dd:.1f}%) has been severe over this window")
                elif dd <= DRAWDOWN_ELEVATED_PCT:
                    risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                    risks.append(f"Max drawdown ({dd:.1f}%) is elevated")

        # --- Average pairwise correlation ---
        symbols_with_returns = list(returns_by_symbol.keys())
        if len(symbols_with_returns) >= 2:
            correlations = []
            for i in range(len(symbols_with_returns)):
                for j in range(i + 1, len(symbols_with_returns)):
                    corr = pearson_correlation(
                        returns_by_symbol[symbols_with_returns[i]],
                        returns_by_symbol[symbols_with_returns[j]],
                    )
                    if corr is not None:
                        correlations.append(corr)
            if correlations:
                avg_corr = sum(correlations) / len(correlations)
                evidence.append(f"Average pairwise correlation across positions is {avg_corr:+.2f}")
                if avg_corr >= CORRELATION_ELEVATED:
                    risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                    risks.append(
                        f"Average pairwise correlation ({avg_corr:+.2f}) is high — "
                        f"positions may not diversify each other as much as their labels suggest"
                    )
                elif avg_corr < 0.3:
                    catalysts.append("Low average correlation across positions supports genuine diversification")

        confidence = round(70.0 * (len(included_positions) / len(portfolio.positions)), 1) if portfolio.positions else 0.0

        return AgentReport(
            department=self.department,
            asset_or_theme=portfolio.name,
            bias=Bias.NEUTRAL,   # the Risk desk assesses risk, not direction — see module docstring
            bias_score=0.0,
            confidence=confidence,
            risk_level=risk_level,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=[],
        )
