# Macro factor normalization recalibration

## How this was found

Not from routine testing — from the user's own live run of
`scripts/demo_agents.py` with a real, working `FRED_API_KEY`. The output
showed 7 of Chief Macro Officer's 16 factors simultaneously clamped at
the exact `+100`/`-100` extreme: PPI, GDP, JOLTS, Initial Jobless Claims,
Consumer Confidence, Housing Starts, and Federal Debt. That's not
plausible as a coincidence — nearly half the factors reading at the
absolute maximum simultaneously pointed at a structural scoring issue,
not a genuinely extreme economic moment.

## Root cause

Two things compounding:

1. `connectors/fred_connector.py`'s `FredConnector` fetches a fixed
   `limit=5` observations for EVERY series, regardless of how often that
   series is actually reported. Five observations is a wildly different
   real time span depending on frequency:
   - Initial Jobless Claims (weekly) → 5 **weeks**
   - Most factors (monthly) → 5 **months**
   - GDP, Federal Debt (quarterly) → ~15 **months**
2. Every one of the 16 factors used the exact same `normalization_pct =
   5.0` — the "% change treated as maximally bullish/bearish" threshold
   — regardless of how naturally volatile that specific series is.

The combination meant:
- **Initial Jobless Claims** and **Housing Starts** are both well-known
  to be genuinely noisy series (weekly reporting noise, weather,
  seasonal-adjustment quirks) — a 5-10%+ move with zero real economic
  significance is routine for both, so a tight 5% band meant they were
  almost *always* going to clamp.
- **GDP** and **Federal Debt** are LEVEL series that compound upward
  under nearly any economic conditions (nominal GDP growing ~4-6%/year
  is completely ordinary; the debt level rises almost every quarter
  under any fiscal regime) — over a 15-month window, a 5%+ cumulative
  move is closer to the norm than the exception, meaning these two
  factors were structurally biased to read as "maximally bullish" and
  "maximally bearish" respectively, almost regardless of whether
  anything unusual was actually happening.

## The fix

Recalibrated `normalization_pct` per factor in
`agents/chief_macro_officer.py`'s `_FACTOR_SPECS`, based on each series'
well-documented real-world characteristics:

| Factor | Old | New | Why |
|---|---|---|---|
| PPI | 5.0 | 10.0 | More volatile than CPI (production-side prices move harder than consumer prices) |
| GDP | 5.0 | 10.0 | A compounding level series — normal growth shouldn't read as maximally bullish |
| JOLTS Job Openings | 5.0 | 10.0 | Genuinely volatile month to month |
| Initial Jobless Claims | 5.0 | 15.0 | The single noisiest series in the list — weekly reporting noise routinely swings it 5-10%+ |
| Consumer Confidence | 5.0 | 10.0 | Can move sharply during genuine sentiment shifts, but needs a wider band than a tight 5% to only flag truly extreme readings |
| Housing Starts | 5.0 | 15.0 | Widely regarded as the noisiest major US economic indicator |
| Federal Debt | 5.0 | 8.0 | A compounding level series — should reflect accelerating growth, not "debt went up again," which it does almost every quarter |

Every other factor (CPI, Core CPI, Core PCE, Retail Sales, Unemployment
Rate, NFP, Average Hourly Earnings, Dollar Index, Credit Spreads) kept
its original 5.0 — the live run showed these producing sensible,
differentiated, non-clamped scores, so there was no evidence they needed
adjusting.

**Honest limitation**: these are reasoned, defensible first-pass
recalibrations based on each series' well-documented general volatility
characteristics — NOT values back-tested against that series' own actual
historical distribution of 5-observation trailing moves, since this
platform has no live network access from this development environment to
compute that. `agents/backtest_engine.py`'s correlation-validation
infrastructure (see `docs/ARCHITECTURE_BACKTESTING.md`) could be extended
to properly calibrate these empirically once real historical data is
available — a natural, concrete next step connecting two things built in
this project.

## Testing

`test_recalibrated_normalization_stops_moderate_moves_from_clamping`
proves the fix is real and factor-specific, not a blanket loosening: an
8% synthetic move no longer clamps Initial Jobless Claims, Housing
Starts, PPI, or JOLTS (all recalibrated), while the SAME 8% move still
correctly clamps CPI (left untouched at 5.0) — proving the recalibration
targeted exactly the factors that needed it, not everything indiscriminately.

568 tests total, all passing, zero regression to any existing behavior.

## Update: the same pattern found again, this time in EIA inventory data

A live run with a real, working `EIA_API_KEY` showed Chief Commodity
Fundamentals Officer's Crude Oil Inventories factor clamped at the exact
`+100.0` extreme — the identical signature that led to this document in
the first place. Same root cause, different data source: the live agent
fetches a 12-observation window (~12 weeks of EIA weekly petroleum
data), and both crude oil and especially natural gas inventories are
known to swing significantly over that span due to well-documented
seasonal patterns (summer driving-season draws, winter heating-season
withdrawals) — a 5%+ move over 12 weeks is often routine seasonal
behavior, not an unusual current condition.

Recalibrated in `agents/chief_commodity_fundamentals_officer.py`'s
`COMMODITY_FACTOR_SPECS`:

| Factor | Old | New | Why |
|---|---|---|---|
| Crude Oil Inventories | 5.0 | 10.0 | Seasonal swings routinely exceed a tight 5% band over a 12-week window |
| Natural Gas Storage | 5.0 | 20.0 | Widened further than crude oil — natural gas has a substantially more pronounced seasonal injection/withdrawal cycle |

Gold's 3 factors (Real Yield, Dollar Index, Fed Funds) were left
untouched at 5.0 — the same live run showed all three producing sensible,
differentiated, non-clamped scores, consistent with the earlier finding
that these specific FRED series (daily market-observed rates, not survey
statistics) don't share the same miscalibration risk.

`test_recalibrated_eia_normalization_stops_moderate_seasonal_moves_from_clamping`
proves the fix directly: the same 8% synthetic seasonal-scale decline no
longer clamps either commodity, and Natural Gas (widened further) scores
measurably closer to neutral than Crude Oil for the identical input —
confirming the two thresholds are genuinely different, not a uniform
blanket change. **595 tests total.**

## Proactive audit: checking whether this same pattern exists elsewhere

Given the same over-clamping bug had now been found and fixed TWICE via
live testing (Macro, Commodity Fundamentals), a direct search was run for
every other call site using `agents.trend_scoring.series_trend_score()`
or `percent_change_score()` — rather than waiting for a third live run to
catch the next instance.

Found three more call sites relying on the implicit uncalibrated `5.0`
default. Handled with different confidence levels, honestly:

- **Chief Cryptocurrency Analyst's Open Interest factor** — widened to
  `20.0`. Crypto derivatives open interest is well-established (not a
  disputed point) to be far more volatile than most financial data —
  10-50%+ swings over the connector's 30-day fetch window are routine
  during any period of meaningful crypto market movement. This is a
  reasoned, proactive fix, explicitly NOT yet confirmed via an actual
  live clamped run the way the other two were.
- **Chief Bond Strategist's 10Y Treasury yield trend** — left unchanged.
  Treasury yields are daily market-observed data with genuinely lower
  natural day-to-day volatility than seasonal/survey data; there isn't a
  strong a priori case this needs adjusting, unlike the other three.
  Worth confirming live rather than guessing.
- **Chief Equity Analyst's EPS/Revenue trend factors** — left unchanged.
  Company growth rates vary enormously by company (a mature value stock
  and a fast-growing tech company have very different "normal" EPS
  growth), so a single uniform correction here would be a much weaker,
  less defensible guess than the other cases. Needs live evidence before
  touching, not general reasoning alone.

`test_open_interest_normalization_widened_beyond_the_uncalibrated_default`
proves the crypto fix directly: an 8% open-interest move — comfortably in
clamping territory under the old 5.0 default — no longer clamps at the
new 20.0 threshold. **596 tests total.**
