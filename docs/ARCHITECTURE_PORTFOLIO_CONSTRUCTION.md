# Portfolio construction — position sizing and multi-asset allocation

## What this adds

Everything built before this answers "what does the data say" (research)
or "would this signal have made money" (strategy backtesting). This adds
the next real piece toward closing the "quant machine" gap: given real
capital and multiple opportunities, how much should go where?

Still purely research/planning. `agents/portfolio_construction.py`
computes a PROPOSED allocation — it does not execute anything, connect
to a broker, or manage real capital. Its output is designed to convert
directly into `models.portfolio.Position` objects, so a proposed
allocation can be fed straight into the existing, already-real Chief
Risk Officer to check the resulting portfolio's actual VaR, volatility,
and correlation before anyone acts on it.

## What's in it

- **`fixed_fractional_size()`** — classic risk-based position sizing:
  how many units so a stop-out costs exactly `risk_pct` of account
  equity. Hand-verified against a simple worked example.
- **`kelly_fraction()`** — the Kelly criterion, with a fractional-Kelly
  multiplier (quarter-Kelly by default, the common real-world
  convention — full Kelly is widely considered too aggressive given
  parameter uncertainty). Verified against the classic textbook example
  (60% win rate, 1:1 payoff → 20% raw Kelly). A losing edge correctly
  clamps to 0%, never a fabricated negative position.
- **`kelly_fraction_from_backtest()`** — a direct, concrete connection
  to `agents/strategy_backtest.py`: computes Kelly sizing straight from
  a real simulated trade history's own win rate and average win/loss,
  rather than requiring those numbers supplied by hand.
- **`volatility_target_weights()`** — inverse-volatility weighting
  across multiple assets, so each contributes roughly equal RISK to the
  portfolio rather than equal capital.
- **`apply_position_constraints()`** — caps any single position, then
  rescales the whole set if still over the gross exposure budget after
  capping.

## Honest scope: correlation is not modeled

`volatility_target_weights()` uses simple inverse-volatility weighting —
each asset's OWN volatility only. Real institutional risk-parity
allocation also accounts for correlation BETWEEN assets via a full
covariance matrix, which this does not attempt. Chief Risk Officer
already computes real pairwise correlation for a given portfolio
(`agents/chief_risk_officer.py`) — building a true correlation-aware
allocator on top of that is a natural, harder follow-up, not attempted
here. Stated plainly in the module's own docstring, not just here.

## A real design decision worth being explicit about

`apply_position_constraints()` does NOT redistribute unused capacity
after capping an oversized position — if capping frees up budget, that
slack is left unallocated (effectively cash) rather than force-fed into
the remaining positions. This is a deliberate, conservative default
(verified directly with a dedicated test proving the total stays at 35%
rather than being rescaled up to 100% after an 80%→25% cap), not an
oversight — a "fully redistribute freed capacity" mode would be a
reasonable future option but adds a real design choice (redistribute
proportionally? equally? by some other rule?) that wasn't worth adding
in this first pass.

## `scripts/build_portfolio.py`

```
python scripts/build_portfolio.py --assets "Gold:GC=F,SPY:SPY,TLT:TLT"
python scripts/build_portfolio.py --assets "Gold:GC=F,SPY:SPY" --max-position-pct 40
```

Fetches REAL price history for each asset, computes REAL annualized
volatility from real daily returns, derives vol-target weights, applies
constraints, and prints a proposed allocation table. Verified end-to-end
with realistic mocked multi-asset data: the lowest-volatility asset
correctly received the largest raw weight, which was then correctly
capped at the configured limit — with the total correctly left below
100% rather than force-filled, matching the tested, documented design.

Deliberately does NOT wire Kelly-from-backtest into this same script —
combining a single Kelly-sized strategy with a multi-asset vol-target
allocation in one CLI invocation would conflate two genuinely different
sizing questions. Both functions are directly importable and composable
in your own script if you want to combine them.

## Testing

20 tests in `tests/test_portfolio_construction.py`:
- Fixed-fractional sizing hand-verified, including the short-stop case
  (stop above entry)
- Kelly verified against the classic textbook example, the fractional
  multiplier, negative-edge clamping to 0, and the zero-avg-loss `None`
  case
- Kelly-from-backtest verified against a hand-computed value from real
  simulated trades, and correctly `None` for too few trades or no losses
- Inverse-volatility weighting verified for the exact proportional
  relationship (half the volatility → exactly double the weight),
  summing to 100%, and correctly excluding zero/negative-volatility
  assets rather than fabricating a weight for them
- Constraint capping, the "no forced redistribution" design decision,
  the down-rescale path when capping alone isn't enough, and explicit
  leverage permission when configured

**657 tests total, all passing.**
