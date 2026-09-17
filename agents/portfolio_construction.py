"""
Portfolio construction — position sizing and multi-asset allocation.

Everything built so far in this platform answers "what does the data
say" (research) or "would this signal have made money" (strategy
backtesting). This module answers a genuinely different question: given
real capital and multiple opportunities, how much should go where?

Still purely research/planning — this computes a PROPOSED allocation. It
does not execute anything, connect to a broker, or manage real capital.
Its output (dollar or unit sizes) is designed to convert directly into
models.portfolio.Position objects, so a proposed allocation can be fed
straight into the existing, already-real Chief Risk Officer to check the
resulting portfolio's actual VaR/volatility/correlation before anyone
acts on it — closing the loop with infrastructure that already exists
rather than duplicating it.

HONEST SCOPE: the volatility-targeting weights below use simple
inverse-volatility weighting, which assumes each asset contributes
independently to portfolio risk. Real institutional risk-parity
allocation also accounts for CORRELATION between assets (via a full
covariance matrix, not just each asset's own volatility) — a genuinely
harder problem this module does not attempt. Chief Risk Officer already
computes real pairwise correlation (agents/chief_risk_officer.py) for a
given portfolio; incorporating that into a true correlation-aware
allocator is a natural, more advanced follow-up, not attempted here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .strategy_backtest import StrategyBacktestResult


def fixed_fractional_size(
    account_equity: float, risk_pct: float, entry_price: float, stop_price: float,
) -> Optional[float]:
    """
    Classic risk-based position sizing: how many units to buy/sell so
    that if price hits the stop, the loss equals exactly `risk_pct` of
    account equity — not a fixed dollar amount or a fixed number of
    shares, which don't account for how far away the stop actually is.

    risk_pct: e.g. 1.0 for "risk 1% of account equity per trade" — a
        common, conservative institutional convention, not a universal
        rule (higher or lower is a real risk-tolerance choice, not
        something this function should assume for you).

    Returns None if entry_price == stop_price (undefined — zero risk
    distance) rather than dividing by zero or fabricating a size.
    """
    per_unit_risk = abs(entry_price - stop_price)
    if per_unit_risk == 0:
        return None
    risk_amount = account_equity * (risk_pct / 100.0)
    return round(risk_amount / per_unit_risk, 4)


def kelly_fraction(
    win_rate_pct: float, avg_win_pct: float, avg_loss_pct: float, kelly_multiplier: float = 0.25,
) -> Optional[float]:
    """
    The Kelly criterion: f* = W - (1-W)/R, where W is win probability and
    R is the payoff ratio (average win size / average loss size). This
    is the growth-optimal bet size in theory — but full Kelly is widely
    considered too aggressive in practice (it assumes the win
    rate/payoff ratio are known with certainty, which they never are
    from a finite historical sample), so `kelly_multiplier` applies a
    FRACTIONAL Kelly (0.25 = "quarter Kelly," a common, more conservative
    real-world convention) rather than the raw theoretical value.

    win_rate_pct: 0-100. avg_win_pct/avg_loss_pct: both POSITIVE
    magnitudes (e.g. avg_loss_pct=2.0 means the average losing trade lost
    2%, not -2%).

    Returns None if avg_loss_pct is 0 (no losses to compute a payoff
    ratio from — matches the same "undefined, not infinite" convention
    agents.strategy_backtest.StrategyBacktestResult.profit_factor
    already uses) or if inputs are otherwise nonsensical (negative
    percentages). A negative raw Kelly (a losing edge) is clamped to
    0.0 — the honest answer to "how much should I bet on a strategy
    with no edge" is nothing, not a fabricated negative position.
    """
    if avg_loss_pct == 0 or avg_win_pct < 0 or avg_loss_pct < 0:
        return None
    if not (0.0 <= win_rate_pct <= 100.0):
        return None

    win_prob = win_rate_pct / 100.0
    payoff_ratio = avg_win_pct / avg_loss_pct
    raw_kelly = win_prob - (1.0 - win_prob) / payoff_ratio
    raw_kelly = max(0.0, raw_kelly)  # a negative edge means "don't bet," not "bet negative"
    return round(raw_kelly * kelly_multiplier * 100, 2)  # as a % of capital


def kelly_fraction_from_backtest(
    result: StrategyBacktestResult, kelly_multiplier: float = 0.25,
) -> Optional[float]:
    """
    Computes Kelly sizing directly from a REAL simulated trade history —
    a direct, concrete connection to agents/strategy_backtest.py rather
    than requiring win rate/payoff ratio to be supplied separately by
    hand. Returns None under the same conditions kelly_fraction() does
    (no losing trades to compute a payoff ratio from), or if there are
    fewer than 5 trades — the same small-sample threshold
    StrategyBacktestResult.interpretation() already uses, since Kelly
    sizing from a handful of trades is not a meaningfully estimated edge.
    """
    if result.num_trades < 5 or result.num_losses == 0:
        return None
    wins = [t.net_return_pct for t in result.trades if t.net_return_pct > 0]
    losses = [t.net_return_pct for t in result.trades if t.net_return_pct < 0]
    if not wins:
        return None
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses))
    return kelly_fraction(result.win_rate, avg_win, avg_loss, kelly_multiplier)


def volatility_target_weights(asset_volatilities: Dict[str, float]) -> Dict[str, float]:
    """
    Inverse-volatility weighting: each asset's weight is proportional to
    1/volatility, normalized to sum to 100%. A lower-volatility asset
    gets a LARGER weight — the standard idea behind risk-parity-style
    allocation, that each position should contribute roughly EQUAL risk
    to the portfolio, not equal capital. See this module's docstring for
    the honest correlation-blindness caveat.

    asset_volatilities: e.g. {"Gold": 15.0, "SPY": 18.0, "TLT": 8.0} —
    annualized volatility (%), the same units
    agents.risk_calculations.annualized_volatility() already produces.

    Assets with a zero or negative volatility (nonsensical/missing data)
    are excluded entirely from the allocation — never given a fabricated
    weight — and the remaining assets' weights are renormalized to still
    sum to 100%.
    """
    usable = {a: v for a, v in asset_volatilities.items() if v is not None and v > 0}
    if not usable:
        return {}
    inverse_vols = {a: 1.0 / v for a, v in usable.items()}
    total = sum(inverse_vols.values())
    return {a: round(iv / total * 100, 2) for a, iv in inverse_vols.items()}


def apply_position_constraints(
    weights: Dict[str, float], max_position_pct: float = 25.0, max_gross_exposure_pct: float = 100.0,
) -> Dict[str, float]:
    """
    Caps any single position at max_position_pct of the portfolio, then
    rescales the WHOLE set (proportionally, preserving relative sizing
    between the remaining positions) if the total still exceeds
    max_gross_exposure_pct after capping — e.g. 100% for a fully-invested,
    no-leverage portfolio; a number above 100% permits leverage,
    deliberately, not by accident.

    This is a real, meaningful order of operations: capping a large
    position first, THEN rescaling everything to fit the gross exposure
    limit, avoids one oversized position silently consuming the entire
    risk budget and starving every other position.
    """
    capped = {a: min(w, max_position_pct) for a, w in weights.items()}
    total = sum(capped.values())
    if total <= max_gross_exposure_pct or total == 0:
        return {a: round(w, 2) for a, w in capped.items()}
    scale = max_gross_exposure_pct / total
    return {a: round(w * scale, 2) for a, w in capped.items()}
