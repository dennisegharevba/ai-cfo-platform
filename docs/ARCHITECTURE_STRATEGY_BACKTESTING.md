# Strategy-level backtesting — simulated trades, not just correlation

## What this adds

`agents/backtest_engine.py` answers "does this signal correlate with
subsequent returns?" — a factor-validation question, already built and
tested. `agents/strategy_backtest.py` answers a genuinely different
question: "if you had actually traded this signal, what would have
happened?" — simulated entries, exits, transaction costs, an equity
curve, and real strategy metrics.

Still purely research. This produces a report about a hypothetical
strategy's historical performance — it does not place trades, connect to
a broker, or manage a real position, the same design this platform has
held to since Phase 1.

## The simulation rule

For each signal reading with `|score| >= entry_threshold` (default 15.0,
matching this platform's own neutral-band convention elsewhere): open a
`long` position if the score is positive, `short` if negative, hold for
`forward_window_days` (default 20), then close. A short position's P&L
is the inverted price move — verified directly (a bearish signal
followed by a real price decline produces a genuine winning short
trade, not a loss). A flat round-trip transaction cost
(`--transaction-cost-bps`, default 5.0) is subtracted from every trade —
an estimate, not a verified real broker figure for any specific venue.

## Metrics computed

- **Win rate, profit factor** — profit factor is `None` (not fabricated
  as infinite) when there are zero losing trades to divide by
- **Total return** — compounded across trades in sequence, not a naive
  sum (verified directly: two +10% trades compound to +21%, not +20%)
- **Max drawdown** — of the STRATEGY's own equity curve, not the
  underlying asset's price history. A strategy that only took winning
  trades correctly shows ~0% drawdown even if the asset itself had a
  real decline somewhere in its own history that the strategy simply
  wasn't in a position for
- **Sharpe / Sortino** — annualized using the forward window as a
  trades-per-year proxy (252 / forward_window_days). Both are `None`
  for fewer than 2 trades, or when there's zero return variance to
  divide by — never fabricated as an undefined ratio

## A real unit-mismatch bug caught before it shipped

The first draft reused `agents.risk_calculations.annualized_volatility()`
for the Sharpe/Sortino denominator. That function assumes DECIMAL-FRACTION
returns (0.01 = 1%) and multiplies by 100 internally to produce a
percentage — but this module's `net_return_pct` values are already in
percentage-point form (5.0 = 5%). Using it directly would have silently
scaled every Sharpe ratio wrong by two orders of magnitude. Caught by
checking the actual function signature and its docstring before wiring
it in, not after. Fixed by reusing `agents.risk_calculations._stdev()`
directly instead — a raw standard deviation with no unit assumption,
which is genuinely what a Sharpe ratio's `mean / stdev` needs (the ratio
is scale-consistent as long as both sides use the same units).

## `scripts/run_strategy_backtest.py`

```
python scripts/run_strategy_backtest.py --signal seasonality --asset Gold
python scripts/run_strategy_backtest.py --signal "Initial Jobless Claims" --asset SPY --entry-threshold 20
python scripts/run_strategy_backtest.py --signal vix --asset SPY --transaction-cost-bps 10
```

Reuses the exact same signal-computation infrastructure as
`scripts/run_backtest.py` (`SIGNAL_FUNCTIONS`, price fetching, FRED rate
pacing) — only the final step (correlation vs. simulated trades) is new.
Prints a full trade log alongside the summary metrics.

## Testing

17 tests in `tests/test_strategy_backtest.py`:
- Below-threshold signals correctly produce no trade
- Long and short direction/P&L verified directly, including the
  short-inversion case
- Missing forward price data is skipped, never fabricated
- Compounding proven directly (not a naive sum)
- Win rate, profit factor (including the "no losses" `None` case)
- Sharpe proven against a hand-computed value using Python's own
  `statistics` module, and proven `None` for zero-variance data rather
  than a fabricated infinite ratio
- Max drawdown proven to reflect the strategy's own equity curve, not
  the asset's
- Transaction costs proven to genuinely reduce net returns

**637 tests total, all passing.** The CLI script verified end-to-end
with realistic mocked price data, producing a complete, internally
consistent trade log and summary.

## What this doesn't do — honest scope

No position sizing beyond one unit per trade, no compounding of position
size with account growth, no slippage model beyond the flat cost
estimate, no overlapping-trade handling (each signal date is treated
independently even if its holding period overlaps a prior trade's), and
no multi-signal/portfolio-level strategy testing (this tests one signal
at a time, the same scope `agents/backtest_engine.py` already has).
