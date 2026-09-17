"""
Strategy-level backtesting — simulates actual trades from a signal and
reports real strategy performance, not just correlation.

agents/backtest_engine.py answers "does this signal correlate with
subsequent returns?" — a factor-validation question. This module answers
a genuinely different question: "if you had actually TRADED this signal,
what would have happened?" — simulated entries, exits, transaction
costs, an equity curve, and real strategy metrics (Sharpe, Sortino, win
rate, profit factor, strategy-level max drawdown).

Still purely research: this produces a REPORT about a hypothetical
strategy's historical performance. It does not place trades, connect to
a broker, or manage any real position — consistent with this platform's
design since Phase 1.

Reuses agents.backtest_engine._forward_return() and
agents.risk_calculations._stdev()/max_drawdown() directly, the same
established pattern already used elsewhere in this project (e.g.
agents/backtest_signals.py reusing chief_macro_officer.py's private
_FACTOR_SPECS/_FRED_SERIES_IDS) — rather than duplicating that logic.
NOTE: agents.risk_calculations.annualized_volatility() was deliberately
NOT reused here — it assumes decimal-fraction returns (0.01 = 1%) and
multiplies by 100 internally, while this module's net_return_pct values
are already in percentage-point form (5.0 = 5%); using it directly would
have silently scaled the Sharpe/Sortino denominator wrong. _stdev()
operates on raw values with no unit assumption, which is what's actually
needed here — caught before shipping, not after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Tuple

from .backtest_engine import _forward_return
from .risk_calculations import _stdev, max_drawdown as _max_drawdown_pct


@dataclass
class TradeRecord:
    entry_date: date
    exit_date: date
    direction: str            # "long" or "short"
    signal_score_at_entry: float
    gross_return_pct: float   # before transaction costs, in the trade's own direction (already sign-flipped for shorts)
    net_return_pct: float     # after round-trip transaction costs
    is_win: bool


@dataclass
class StrategyBacktestResult:
    signal_name: str
    asset: str
    entry_threshold: float
    forward_window_days: int
    transaction_cost_bps: float
    trades: List[TradeRecord] = field(default_factory=list)
    skipped_dates: int = 0   # signal dates that didn't cross the threshold, or had no matching forward price

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def num_wins(self) -> int:
        return sum(1 for t in self.trades if t.is_win)

    @property
    def num_losses(self) -> int:
        return self.num_trades - self.num_wins

    @property
    def win_rate(self) -> Optional[float]:
        if self.num_trades == 0:
            return None
        return round(self.num_wins / self.num_trades * 100, 1)

    @property
    def profit_factor(self) -> Optional[float]:
        """Sum of winning trades' returns divided by the absolute sum of
        losing trades' returns. None if there are no losses to divide by
        (undefined, not infinite — never fabricated) or no trades at all."""
        if not self.trades:
            return None
        gross_wins = sum(t.net_return_pct for t in self.trades if t.net_return_pct > 0)
        gross_losses = sum(t.net_return_pct for t in self.trades if t.net_return_pct < 0)
        if gross_losses == 0:
            return None
        return round(gross_wins / abs(gross_losses), 2)

    @property
    def total_return_pct(self) -> Optional[float]:
        """Compounded return across every trade in sequence (each
        trade's capital is the prior trade's ending capital) — not a
        simple sum, since that would misrepresent how returns actually
        compound trade over trade."""
        if not self.trades:
            return None
        equity = 1.0
        for t in self.trades:
            equity *= (1.0 + t.net_return_pct / 100.0)
        return round((equity - 1.0) * 100, 2)

    @property
    def equity_curve(self) -> List[float]:
        """Cumulative equity after each trade, starting at 100 — the
        basis for max_drawdown_pct below."""
        equity = 100.0
        curve = [equity]
        for t in self.trades:
            equity *= (1.0 + t.net_return_pct / 100.0)
            curve.append(equity)
        return curve

    @property
    def max_drawdown_pct(self) -> Optional[float]:
        """Max peak-to-trough decline of the STRATEGY's own equity curve
        — genuinely different from the underlying asset's own max
        drawdown, since a short-capable strategy can profit (and draw
        down) on moves the asset's own price history wouldn't reflect."""
        if not self.trades:
            return None
        return _max_drawdown_pct(self.equity_curve)

    @property
    def sharpe_ratio(self) -> Optional[float]:
        """Mean trade return / stdev of trade returns (both in the same
        percentage-point units, so the ratio is scale-consistent),
        annualized using the forward window as the holding-period proxy
        (252 trading days / forward_window_days ~= trades per year).
        None for fewer than 2 trades (no variance to compute) or zero
        variance (a degenerate, uninformative case)."""
        if len(self.trades) < 2:
            return None
        returns = [t.net_return_pct for t in self.trades]
        mean_return = sum(returns) / len(returns)
        stdev = _stdev(returns)
        if stdev is None or stdev == 0:
            return None
        trades_per_year = 252.0 / max(self.forward_window_days, 1)
        return round((mean_return / stdev) * (trades_per_year ** 0.5), 2)

    @property
    def sortino_ratio(self) -> Optional[float]:
        """Same as Sharpe, but only penalizing downside variance —
        upside volatility isn't treated as 'risk.'"""
        if len(self.trades) < 2:
            return None
        returns = [t.net_return_pct for t in self.trades]
        mean_return = sum(returns) / len(returns)
        downside = [r for r in returns if r < 0]
        if len(downside) < 2:
            return None
        downside_dev = (sum(r ** 2 for r in downside) / len(downside)) ** 0.5
        if downside_dev == 0:
            return None
        trades_per_year = 252.0 / max(self.forward_window_days, 1)
        return round((mean_return / downside_dev) * (trades_per_year ** 0.5), 2)

    def to_dict(self) -> dict:
        return {
            "signal_name": self.signal_name,
            "asset": self.asset,
            "entry_threshold": self.entry_threshold,
            "forward_window_days": self.forward_window_days,
            "transaction_cost_bps": self.transaction_cost_bps,
            "num_trades": self.num_trades,
            "num_wins": self.num_wins,
            "num_losses": self.num_losses,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "skipped_dates": self.skipped_dates,
        }

    def interpretation(self) -> str:
        if self.num_trades < 5:
            return f"Only {self.num_trades} simulated trade(s) — too few to draw any real conclusion."
        parts = [
            f"{self.signal_name} vs. {self.asset}: {self.num_trades} simulated trades "
            f"({self.num_wins}W/{self.num_losses}L, {self.win_rate}% win rate)."
        ]
        if self.total_return_pct is not None:
            parts.append(f"Compounded return: {self.total_return_pct:+.1f}%.")
        if self.sharpe_ratio is not None:
            parts.append(f"Sharpe: {self.sharpe_ratio:.2f}.")
        if self.max_drawdown_pct is not None:
            parts.append(f"Max strategy drawdown: {self.max_drawdown_pct:.1f}%.")
        if self.profit_factor is None and self.num_losses == 0 and self.num_trades > 0:
            parts.append("No losing trades in this sample — profit factor undefined, not infinite.")
        parts.append(
            "This is a hypothetical, unmanaged simulation (fixed holding period, no position sizing "
            "beyond one unit per trade, no slippage beyond the flat cost below) — a real strategy's "
            "results would differ."
        )
        return " ".join(parts)


def simulate_strategy(
    signal_name: str,
    asset: str,
    signal_scores: List[Tuple[date, float]],
    price_history_oldest_first: List[Tuple[date, float]],
    forward_window_days: int = 20,
    entry_threshold: float = 15.0,
    transaction_cost_bps: float = 5.0,
) -> StrategyBacktestResult:
    """
    signal_scores: list of (as_of_date, bias_score) — the same shape
    agents.backtest_engine.run_backtest() takes.
    entry_threshold: minimum |bias_score| to trigger a trade. Below this,
        the date is skipped (flat — no trade), matching the platform's
        own bias_from_score() convention that scores within a neutral
        band aren't a real directional signal.
    transaction_cost_bps: round-trip cost in basis points (entry + exit
        combined), a flat estimate — NOT a real broker's actual
        commission/spread/slippage, which vary by asset and venue. E.g.
        5.0 bps = 0.05% round-trip, a reasonable rough estimate for a
        liquid futures/ETF market, not a verified real-world figure for
        any specific broker.

    Never fabricates a trade: any signal date whose forward return can't
    be found in the price history is skipped and counted in
    skipped_dates, exactly like agents.backtest_engine.run_backtest().
    """
    trades: List[TradeRecord] = []
    skipped = 0

    for as_of_date, score in signal_scores:
        if abs(score) < entry_threshold:
            skipped += 1
            continue

        fwd_return = _forward_return(price_history_oldest_first, as_of_date, forward_window_days)
        if fwd_return is None:
            skipped += 1
            continue

        direction = "long" if score > 0 else "short"
        # A short position profits when price FALLS — invert the raw
        # forward return so gross_return_pct always represents THIS
        # trade's own P&L direction, not the asset's raw price change.
        gross_return_pct = fwd_return if direction == "long" else -fwd_return
        # transaction_cost_bps IS the full round-trip cost already (entry + exit combined).
        net_return_pct = gross_return_pct - (transaction_cost_bps / 100.0)

        target_date = as_of_date + timedelta(days=forward_window_days)
        exit_date = as_of_date
        for d, _price in price_history_oldest_first:
            if d >= target_date:
                exit_date = d
                break

        trades.append(TradeRecord(
            entry_date=as_of_date, exit_date=exit_date, direction=direction,
            signal_score_at_entry=score, gross_return_pct=round(gross_return_pct, 3),
            net_return_pct=round(net_return_pct, 3), is_win=net_return_pct > 0,
        ))

    return StrategyBacktestResult(
        signal_name=signal_name, asset=asset, entry_threshold=entry_threshold,
        forward_window_days=forward_window_days, transaction_cost_bps=transaction_cost_bps,
        trades=trades, skipped_dates=skipped,
    )
