# Institutional Fundamental Scoring Engine — Seasonality, Sentiment, and Risk

## Completing the engine's remaining categories

Per the original spec's Final Investment Committee table (Macro, Commodity
Fundamentals, Technical, Sentiment, COT, Seasonality), and per the
explicitly-scoped rollout across earlier deliveries (Macro, then Commodity
Fundamentals), this delivery adds the three remaining categories:
**Seasonality** (new), **Sentiment** (integrated with the existing Phase 5
agent), and **Risk** (new, per-asset). All three reuse
`agents/fundamental_scoring_engine.py`'s `score_category()` — no new
aggregation logic was needed for any of them, the fourth and fifth proof
that the engine genuinely generalizes.

## Seasonality — a genuinely new category, but honestly scoped

`agents/seasonality_scoring.py` + `agents/chief_seasonality_officer.py`.

**The most important thing to understand about this category**: the
monthly scores are WELL-KNOWN, WIDELY-CITED seasonal tendencies from
financial literature and market commentary (gold's historical strength
around Indian wedding season/Chinese New Year demand, "sell in May" for US
equities, winter heating demand for natural gas, planting/harvest pressure
for row crops) — NOT a statistical backtest this platform computed. This
platform has no historical price database to run that analysis against,
and presenting a precise computed statistic without having actually
computed it would be a fabrication. Every score is deliberately moderate
(capped at ±25, verified by a test —
`test_every_score_is_within_moderate_bounds`), reflecting that this is a
supporting signal, not a primary driver — matching the spec's own Final
Investment Committee weighting for Seasonality (10%, the same tier as COT).

Configured assets: Gold, WTI Crude Oil, Natural Gas, Corn, Wheat,
Soybeans, S&P500, NASDAQ100. Every other asset gets an honest "no
seasonality pattern configured" result — no fabricated pattern for
assets this module doesn't actually cover.

**Architecturally distinct**: `ChiefSeasonalityOfficer` is NOT a
`BaseAgent` — it fetches no data through the `DataIntegrityManager` at
all, mirroring the same "pure computation" shape already established by
`ChiefStrategyOfficer`/`ChiefExecutionOfficer`. A calendar lookup needs no
data-fetching machinery, and forcing one would be architectural padding.
This also means Seasonality is the one category that keeps producing real
signal even with zero network access — verified live: running
`scripts/run_daily_cycle.py` in this network-isolated sandbox still
produced correct, real Seasonality scores for every configured asset
(Gold +15 for August "pre-wedding-season buying," matching the table exactly).

`DEFAULT_DEPARTMENT_WEIGHTS["Chief Seasonality Officer"] = 0.3` — the
lowest weight of any department, even below COT's 0.4, since a documented
historical pattern is a genuinely different epistemic category from
live-measured positioning data.

## Sentiment — integrated additively, zero regression to existing logic

`agents/chief_sentiment_officer.py` (Phase 5) already computed a real
news-headline-sentiment score (plus an optional COT-crowd-sentiment blend)
using its own weighted-blend math. Rather than rewrite that working,
tested logic to match `score_category()`'s shape — real regression risk
for no functional benefit — the existing computation was left completely
UNCHANGED, and its already-computed scores are ALSO packaged into
`FundamentalFactor` entries in `factor_breakdown`, purely additively. The
existing 6 tests pass completely unchanged; 4 new tests specifically
prove the addition doesn't touch the pre-existing bias_score/confidence
math (`test_factor_breakdown_does_not_affect_existing_bias_score_computation`
asserts the exact confidence figure the original math has always produced).

**A real bug caught and fixed during this edit**: a `str_replace` call
matched only a function's `def` line (not its full body) while inserting
new tests, orphaning the original test's body with no function
declaration of its own. Caught immediately by re-checking the file's
function list after the edit, not assumed correct.

## Risk — per-asset volatility/drawdown, reusing existing tested math

`agents/chief_risk_fundamentals_officer.py` — genuinely new code, but
built entirely from pieces that already existed and were already tested:
`agents/risk_calculations.py`'s `daily_returns`/`annualized_volatility`/
`max_drawdown` (Phase 6, used by the portfolio-level Chief Risk Officer)
and the existing `YahooHistoryConnector`. No new math, no new connector,
no fabrication — just applying proven tools to a single asset instead of
a portfolio.

**Honest scope on why the rest of the spec's "Risk Assessment" list isn't
duplicated here**:
- **Correlation** and **Portfolio Risk** are inherently portfolio-level
  concepts — they need multiple positions to correlate against, which a
  single asset doesn't have. Already covered by the existing
  `agents/chief_risk_officer.py`.
- **Event Risk** is covered by the separate Institutional Trade Decision
  Engine's `agents/asset_risk_officer.py` (`EVENT_RISK_KEYWORDS`),
  deliberately kept as its own feature per an earlier explicit scoping
  decision — not duplicated into the main pipeline.
- **Liquidity Risk** (bid-ask spreads, market depth) has no free
  structured live source this platform integrates.

### A real architectural question surfaced, and resolved by extending an existing pattern

Chief Risk Fundamentals Officer's score frames low volatility as
favorable and high volatility as unfavorable — but this is a claim about
STABILITY, not a claim that the asset will rise. Folding it into
`ChiefStrategyOfficer`'s directional bias average the same way a Macro or
Sentiment reading is would misrepresent what the signal actually means.
The portfolio-level Chief Risk Officer already had exactly this problem
solved via a dedicated `risk_report` parameter (bias excluded, risk_level/
risks/catalysts included) — but it only accepted a SINGLE report.
`ChiefStrategyOfficer.synthesize()` gained a new `risk_reports` (plural)
parameter, treating any number of risk-type reports identically to the
existing singular one; `risk_report` itself is completely unchanged for
full backward compatibility. `scripts/run_daily_cycle.py`'s `run_cycle()`
now separates "risk_fundamentals" department reports into this new
parameter rather than folding them into the regular directional `reports`
list — a real integration gap that would have silently defeated the whole
point of the exclusion if left unfixed; caught by re-reading the actual
loop, not assumed to route correctly just because `ChiefStrategyOfficer`
itself was updated.

Verified live: `test_risk_fundamentals_department_excluded_from_bias_weighting_in_real_cycle`
runs the real `run_cycle()` (not just `ChiefStrategyOfficer.synthesize()`
in isolation) with a bullish Macro report and a maximally degraded
(zero-confidence, HIGH-risk) risk report, proving the overall bias stays
bullish while risk_level correctly escalates.

## Wired into every real touchpoint

- `agents/__init__.py` exports both new agent classes
- `scripts/run_daily_cycle.py` — new `seasonality` and `risk_fundamentals`
  department runners; `RISK_DEPARTMENT_KEYS` routes the latter through the
  new `risk_reports` parameter
- `config/watchlist.py` — every commodity now also carries `seasonality`
  and (where a Yahoo Finance futures ticker exists —
  `COMMODITY_YAHOO_TICKERS`) `risk_fundamentals`; two new entries
  ("S&P500" via SPY, "NASDAQ100" via QQQ) specifically exercise the
  equity-index seasonality patterns. Equities in the ~357-ticker weekly
  watchlist deliberately do NOT get `risk_fundamentals` added — doing so
  would triple that cycle's already-heavy weekly request volume
  (~350 more Yahoo Finance calls) without an explicit request to take on
  that cost; a natural future addition, not silently added here.
- Dashboard's Department Reports page — both new departments added, each
  verified with a dedicated `AppTest` interaction test (not assumed to
  work just because the generic pattern held for other departments)

## Testing

- 10 tests for `agents/seasonality_scoring.py`, 7 for
  `agents/chief_seasonality_officer.py`
- 4 new tests for Chief Sentiment Officer's additive `factor_breakdown`
  (6 pre-existing tests unchanged and still passing)
- 6 tests for `agents/chief_risk_fundamentals_officer.py`
- 3 new tests for `ChiefStrategyOfficer`'s `risk_reports` parameter, plus
  1 real end-to-end test in `scripts/run_daily_cycle.py`'s test suite
- 2 new dashboard interaction tests (Seasonality, Risk Fundamentals)
- 469 tests total, all passing; the full daily cycle re-run live,
  confirming every new category produces genuinely correct output even
  with zero network access in this environment (Seasonality, being pure
  calendar computation, produces real non-degraded scores; everything
  data-dependent correctly shows zero confidence / HIGH risk)

## What's still not built

- The full "hedge fund research terminal" dashboard redesign (now
  built — see `docs/ARCHITECTURE_DASHBOARD_REDESIGN.md`)
- The "Explain Every Decision" auto-explanation generator (now built —
  see `docs/ARCHITECTURE_DECISION_EXPLANATION.md`)
- `risk_fundamentals` for the equity watchlist (originally deliberately
  deferred here — since reversed, per an explicit later request; see the
  update below)
- Wiring `agents/market_regime.py`'s dynamic weighting into
  `ChiefStrategyOfficer`'s actual department-weighting logic

## Update: risk_fundamentals extended to every asset class (currency, equities, crypto)

Per an explicit later request ("wire everything in... commodities and
equity and currency and crypto currency"),
`agents.chief_risk_fundamentals_officer.ChiefRiskFundamentalsOfficer` is
now wired into `config/watchlist.py` across every asset class this
platform covers, not just commodities:

- **Currency (FX)** — `FX_YAHOO_TICKERS` maps each configured pair to
  Yahoo's FX ticker convention (e.g. `EURUSD=X` for pairs quoted XXX/USD,
  `JPY=X` for pairs quoted USD/XXX — the same best-effort, not-live-
  verified caveat as every other "verify against a real source" file in
  this project: `config/cftc_markets.py`, `config/sp500_tickers.py`,
  `config/fomc_meeting_dates.py`). `DXY` (the Dollar Index itself, not a
  currency pair) uses a different Yahoo ticker convention entirely
  (`DX-Y.NYB`) and is flagged as the single least-confident entry in the
  mapping.
- **Equities** — all ~357 tickers in `WATCHLIST_WEEKLY` now carry
  `risk_fundamentals`, using each ticker directly (no mapping needed —
  equity tickers are already Yahoo-compatible). This REVERSES the earlier
  documented decision (above) that deliberately excluded equities
  specifically because of the added weekly request volume (~350 more
  Yahoo Finance calls). That tradeoff is now accepted explicitly, not
  silently — the module docstring states it plainly rather than
  pretending the earlier concern never existed.
- **Crypto** — `CRYPTO_YAHOO_TICKERS` maps `"BTC"` to `"BTC-USD"`, Yahoo's
  well-established crypto ticker convention (the most confident of the
  three new mappings, since it's widely documented and consistently used).

No changes were needed to `agents/chief_risk_fundamentals_officer.py`
itself, or to `scripts/run_daily_cycle.py`'s `_run_risk_fundamentals`
runner — both were already fully generic (any ticker string works), so
this was purely a `config/watchlist.py` wiring change.

**6 new tests** (`tests/test_watchlist.py`) lock in the actual coverage
counts directly — not just "the department key resolves to a handler"
(already covered elsewhere) but "every FX pair with a known ticker
actually has the department," "equity coverage is complete (357 of 357),
not partial," and "a currency pair with NO known Yahoo ticker does NOT
get a fabricated entry" — so a future change that silently narrowed
coverage back down would fail a test, not just go unnoticed.

Verified live: the daily cycle re-run shows every FX pair and BTC with
2 departments (up from 1); a direct 3-ticker slice of the weekly equity
cycle confirms `department_count: 2` for AAPL/MSFT/GOOGL, with
`Chief Risk Fundamentals Officer` correctly degrading (no network access
in this environment) rather than crashing. **493 tests total.**
