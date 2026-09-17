# The full pipeline — real data through to a real rebalance plan

## What this ties together

Everything built across this session, in one script:
real price history → real volatility → real vol-target portfolio
weights → real broker account state → a real rebalance plan. This is
the natural capstone of the quant-machine roadmap — not new logic, but
the first script that runs the *whole* chain in one command against a
real account.

`scripts/run_full_pipeline.py` duplicates none of the underlying logic —
it imports `_fetch_price_history()` from `scripts/run_backtest.py`,
`annualized_volatility()` from `agents/risk_calculations.py`,
`volatility_target_weights()`/`apply_position_constraints()` from
`agents/portfolio_construction.py`, and `plan_rebalance()`/
`execute_rebalance()` from `agents/execution_engine.py` — every piece
already independently built and tested elsewhere in this project.

## Safety

Same model as every other script in the execution layer: `dry_run` is
the default, `--submit` is required to actually place orders, and
there is no live-trading flag anywhere in this file. Connects to
Alpaca's paper endpoint only, with the same `assert broker.is_paper`
safety check used in `scripts/demo_execution_engine.py` and
`scripts/monitor_risk.py`.

## Verified end-to-end with mocked data

Run against realistic mocked price data and a mocked paper account
(zero real network access from this environment), the full 5-step chain
produced a completely consistent result: two assets' volatilities
computed from real-shaped daily returns, inverse-volatility weights
correctly capped at the configured position limit (both assets' raw
weights exceeded 35%, so both were correctly capped to exactly 35%, with
the remaining 30% correctly left unallocated — the same tested,
documented "no forced redistribution" behavior from
`agents/portfolio_construction.py`), share quantities correctly sized
from the account's real equity and each asset's real current price, and
the dry-run guarantee proven directly: only 2 API calls were mocked
(account + positions), and the script completed cleanly with no attempt
at a third call — if the dry-run protection had failed and order
submission had actually fired, the script would have crashed immediately
on the unmocked call.

## Usage

```
python scripts/run_full_pipeline.py --assets "AAPL:AAPL,SPY:SPY"
python scripts/run_full_pipeline.py --assets "AAPL:AAPL,SPY:SPY" --submit
```

## Live milestone: the first real, complete rebalance

Run for real against a live paper account with `--submit`, this script
executed the platform's first ever real rebalance, end to end. Starting
from 1 AAPL share, it correctly computed a target of ~35% AAPL / 35%
SPY, planned the exact orders needed, submitted them, and the account
came back holding 115.25 AAPL and 45.01 SPY — within 0.08% and 0.03% of
the exact planned quantities respectively, the small remaining
difference fully explained by real price movement between when the plan
was computed and when the order actually filled a moment later, not any
error in the pipeline. A follow-up run correctly detected the account
already matched the target and proposed no further trades — itself a
confirmation the rebalance succeeded, not a failure to submit.

## Honest scope

This is an orchestration script, not new logic — no dedicated test
file, following the same precedent already established for
`scripts/build_portfolio.py` and `scripts/demo_execution_engine.py`.
Correctness rests on the extensive existing test coverage of each piece
it calls, plus the direct end-to-end smoke test described above.
