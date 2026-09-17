# Live risk monitoring — the fourth piece of the quant-machine roadmap

## What this adds

Everything before this either researches, backtests, or (with
`agents/execution_engine.py`) plans/submits trades. This adds
continuous risk oversight: real-time drawdown tracking against
configurable thresholds, tied to the already-real Chief Risk Officer for
actual portfolio-level VaR, volatility, and correlation.

## Read-only by design — a meaningfully lower-risk surface than execution

Nothing in `agents/circuit_breaker.py` or `agents/risk_monitor.py` can
place, modify, or cancel an order. `take_risk_snapshot()` only calls
`broker.get_account()` and `broker.get_positions()` — proven directly
with a broker whose order-submission method raises if called at all.
That's why this module doesn't need the same multi-layer opt-in
structure `agents/execution_engine.py` required: there's no dry-run
distinction to make when nothing here can act in the first place.

`scripts/monitor_risk.py` still connects to Alpaca's PAPER endpoint only
— consistent with every other script in this project — and, like
`scripts/demo_execution_engine.py`, offers no live-trading flag at all.

## The circuit breaker

`agents/circuit_breaker.py`'s `check_circuit_breaker()` is deliberately
pure — no side effects, no broker access, just threshold math given
three numbers (current equity, today's starting equity, all-time peak
equity). Two independent checks, both evaluated and both reported if
both are breached simultaneously (proven directly, not just the first
one found):

- **Daily loss**: has today's equity fallen `max_daily_loss_pct` or more
  from where it started today?
- **Total drawdown**: has equity fallen `max_total_drawdown_pct` or more
  from its all-time peak? Proven directly to trigger independently of
  daily P&L — a slow multi-day bleed with small daily losses each day
  still trips this check even when the daily-loss check alone wouldn't.

The exact boundary case is proven directly: a loss of precisely
`-max_daily_loss_pct%` triggers (`>=`, not requiring the limit to be
exceeded), and one basis point under it does not.

**What this module deliberately does NOT do**: decide what happens on a
halt. That's the caller's responsibility — blocking new orders, sending
an alert, or something else entirely. Keeping the threshold math
completely separate from any action keeps it independently testable and
free of side effects.

## The risk monitor

`agents/risk_monitor.py`'s `take_risk_snapshot()` ties it together:
fetches real account/positions from a broker, converts positions into
the existing `models.portfolio.Portfolio` shape (short positions
correctly preserved as negative quantities), runs them through the
already-tested `ChiefRiskOfficer` for real risk metrics, and checks the
circuit breaker against current equity — returning one combined
snapshot.

**An empty portfolio produces `risk_report=None`, not a fabricated empty
report** — proven directly. There's nothing to analyze, so nothing is
invented.

**A non-empty portfolio always produces a real report object** — proven
directly, including the case (the only one testable from this
environment, with no network access) where the underlying price data is
genuinely unreachable. It degrades exactly the way `ChiefRiskOfficer`
already does on its own (confidence 0, a real listed data gap) rather
than crashing or silently staying `None`.

## `scripts/monitor_risk.py`

```
python scripts/monitor_risk.py
python scripts/monitor_risk.py --loop --interval-seconds 300
python scripts/monitor_risk.py --max-daily-loss-pct 3 --max-drawdown-pct 10
```

Default: one snapshot, then exit. `--loop` monitors continuously,
tracking the day's starting equity and the all-time peak equity ACROSS
iterations — the starting-equity reference resets when the calendar day
changes; the peak reference deliberately does not, since it tracks the
all-time high regardless of day boundaries. On a circuit-breaker trip,
sends a real alert via the SAME `TelegramAlerter` already built and
proven working earlier in this project — no new alerting code.

## Honest, shared limitation

Like the rest of the execution layer, this has not been exercised
end-to-end against a real broker from this environment — no network
access, no real account. The threshold MATH is independently tested and
verified by hand; the real-broker wiring has not been. Test against a
real Alpaca paper account before relying on this for anything.

## Testing

17 new tests across `tests/test_circuit_breaker.py` and
`tests/test_risk_monitor.py` — the circuit breaker's exact-boundary
behavior, both-breaches-simultaneously reporting, zero-equity
divide-by-zero safety, and the risk monitor's empty-vs-populated-report
distinction, correct is_paper/equity propagation, and the read-only
guarantee proven against a broker that would raise if any order-related
method were called.

**715 tests total, all passing.**
