# Institutional Fundamental Scoring Engine

## What this upgrade replaces

Per the upgrade spec, the platform's Chief Fundamental Officer research
engine no longer produces a market bias primarily from COT. Instead, every
major macroeconomic/fundamental factor is evaluated INDEPENDENTLY — its
own current/previous/forecast/surprise reading, its own bullish/bearish/
neutral status, its own 1-10 importance weight, its own confidence score,
its own timestamp and source — before contributing to a category-level
score, which then feeds the existing `ChiefStrategyOfficer` synthesis
completely unchanged.

**This is Phase 1 of a larger, explicitly-scoped build** (three clarifying
questions were asked and answered before any code was written):
1. Technical Confirmation stays OUT of the main engine — Chief Technical
   Officer remains fully removed (see
   `docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md`); this spec's overlap
   with that section was deliberately dropped, not silently reintroduced.
2. Line items with no free live data source (mine production, central
   bank gold buying, jewellery demand, storage levels, cost of production,
   Fear & Greed index, put/call ratio, social sentiment) are SKIPPED
   entirely for now, not faked or stubbed.
3. This phase covers Macro factor expansion + the scoring engine core.
   Commodity Fundamentals, Sentiment, Risk, and Seasonality categories
   follow later, using this exact same `score_category()` pattern.

## A fourth additive layer, not a replacement

Every prior upgrade in this codebase has been additive (Trade Decision
Engine, Institutional Relationship Engine, Technical Officer removal,
Commercial Traders removal) — this one follows the same rule. The existing
`AgentReport` → `ChiefStrategyOfficer` → `ChiefLearningOfficer` →
`ChiefExecutionOfficer` pipeline is completely unchanged. What's new sits
UNDER `ChiefMacroOfficer` (and will sit under future category agents):

```
FundamentalFactor (one per line item: CPI, GDP, NFP, ...)
        |
        v
score_category()  <- generic aggregation, reused for every category
        |
        v
CategoryScore (one per category: "Macroeconomic")
        |
        v
ChiefMacroOfficer._build_report()  <- maps CategoryScore onto a standard
        |                              AgentReport (bias/bias_score/
        |                              confidence/risk_level unchanged
        |                              in shape), PLUS attaches the full
        |                              factor list via the new
        |                              AgentReport.factor_breakdown field
        v
AgentReport  <- flows into ChiefStrategyOfficer exactly as before
```

`AgentReport.factor_breakdown` defaults to an empty list, so every
department that HASN'T been upgraded to this engine yet (Bond, Commodity,
FX, Equity, Crypto, Sentiment) keeps constructing `AgentReport` exactly as
before — zero regression risk, proven by the full existing test suite
passing unchanged (366 tests, only net-new ones added).

## `models/fundamental_factor.py`

`FundamentalFactor`: one independently-scored line. `forecast_value` and
its derived `surprise` property are `Optional` and typically `None` — this
platform has no free source of economist consensus forecasts (FRED and
similar free sources report ACTUAL published values). Left `None` rather
than fabricated, per the standing "never fabricate a number you don't
have" rule going back to Phase 1's Data Integrity Manager.

`FactorBias`: a deliberately simpler tri-state (Bullish/Bearish/Neutral)
than the platform-wide 5-level `Bias` enum, matching the spec's explicit
per-factor ask. Category and department-level bias still use the existing
5-level `Bias` (via `bias_from_score`) for consistency with every other
`AgentReport` in the platform — only individual factor lines use the
simpler tri-state.

`CategoryScore`: the aggregate — score, confidence, bias, risk_level,
and a `disagreement` figure (how much the category's own factors conflict
with each other), computed by `agents/fundamental_scoring_engine.py`.

## `agents/fundamental_scoring_engine.py` — `score_category()`

Deliberately reuses `agents/weighted_stats.py`'s `weighted_mean`/
`weighted_stdev` (newly extracted from `ChiefStrategyOfficer`, which
previously had these as private functions) rather than inventing a second
"combine several scored things into one" formula. Each factor's effective
weight is `importance_weight * (confidence / 100)` — the same "confidence
scales trust" pattern used everywhere else in this platform (a factor with
`importance_weight=9` but `confidence=0`, e.g. missing data, contributes
NOTHING, exactly like a missing department contributes nothing to
`ChiefStrategyOfficer`'s synthesis).

An empty factor list, or a factor list where every factor has zero
effective weight, returns `category_score=0.0`, `bias=NEUTRAL`,
`risk_level=HIGH` — never a fabricated conclusion from nothing, matching
the same contract `DataIntegrityManager` established in Phase 1.

## `agents/market_regime.py` — dynamic weighting, honestly scoped

The spec asks for weights that "dynamically adjust... depending on market
conditions" rather than fixed weights. **What's built is a small,
deterministic, rule-based classifier — not a self-learning system.** The
spec's language could be read as asking for something that tunes itself
from historical backtested outcomes; building that properly would need a
real backtesting harness against historical data, which is a substantial
project of its own — the same honest-scope call already made for
`agents/institutional_relationship.py`'s confidence-adjustment constants
(see `docs/ARCHITECTURE_INSTITUTIONAL_RELATIONSHIP_ENGINE.md`).

`classify_regime(reference_date, fomc_meeting_dates)` returns a set of
active `MarketRegime` flags (`FOMC_WEEK`, `EARNINGS_SEASON`, `NORMAL`),
each toggled by a genuinely determinable condition — a real calendar date
falling in a 4-day FOMC window, or a real calendar month falling in one of
the four well-known earnings-season windows — not an inferred/guessed
condition. `regime_adjusted_weight()` applies each active regime's
category-specific multiplier (e.g. FOMC week → Macro weight × 1.4)
multiplicatively.

**`config/fomc_meeting_dates.py` ships EMPTY, deliberately.** The Fed
publishes its schedule up to ~2 years ahead, but this platform has no live
connector for it, and reconstructing specific calendar dates from training
data would be exactly the kind of unverified guess this platform's other
"best-effort" data files (`config/cftc_markets.py`,
`config/sp500_tickers.py`) explicitly warn against presenting as fact.
With an empty list, `FOMC_WEEK` simply never triggers — the same honest
"visibly incomplete, never silently wrong" behavior used throughout. The
file's own docstring links to where to get the real schedule
(federalreserve.gov) and shows the exact format to paste it in.

This mechanism is built now but its practical effect is small until more
categories exist to weight against each other (with just Macro built out,
there's only one category's weight to adjust) — it becomes meaningful once
Commodity Fundamentals/Sentiment/Risk/Seasonality are added in later phases.

## Chief Macro Officer — the 16 real factors

All via the existing `FredConnector` (no new connector needed) — free, no
new dependency:

| Factor | FRED Series | Direction convention |
|---|---|---|
| CPI (Headline, YoY) | CPIAUCSL | falling = bullish |
| Core CPI (YoY) | CPILFESL | falling = bullish |
| PPI | PPIACO | falling = bullish |
| Core PCE (Fed's preferred gauge) | PCEPILFE | falling = bullish |
| GDP | GDP | rising = bullish |
| Retail Sales | RSAFS | rising = bullish |
| Unemployment Rate | UNRATE | falling = bullish |
| Nonfarm Payrolls | PAYEMS | rising = bullish |
| Average Hourly Earnings | CES0500000003 | rising = bullish (growth read) |
| JOLTS Job Openings | JTSJOL | rising = bullish |
| Initial Jobless Claims | ICSA | falling = bullish |
| Trade-Weighted Dollar Index | DTWEXBGS | falling = bullish (general risk regime) |
| Credit Spreads (ICE BofA US Corp OAS) | BAMLC0A0CM | falling = bullish |
| Consumer Confidence (U. Michigan) | UMCSENT | rising = bullish |
| Housing Starts | HOUST | rising = bullish |
| Federal Debt (Total Public Debt) | GFDEBTN | falling = bullish (low weight, slow-moving) |

Each factor's `importance_weight` (1-10) reflects a defensible, documented
real-world judgment of how closely-watched that release typically is (Core
PCE at 9, since it's the Fed's explicitly stated preferred gauge; Average
Hourly Earnings at 4, since it's a genuinely double-edged signal for
growth vs. inflation and was deliberately kept at moderate weight rather
than picking a side strongly).

**Deliberately NOT included** — no free structured live source exists:
PMIs (ISM's own data is paid, no free FRED substitute for the actual
indices), explicit Fed/ECB/BoE policy-statement analysis (would need NLP
over central bank text, not a numeric data feed), QT/QE as a distinct
tracked line (only implied by the debt/credit-spread factors, not modeled
separately), explicit geopolitical risk (no structured free feed).
Interest Rates/Treasury Yields/Yield Curve are deliberately NOT duplicated
here either — they remain owned by the existing
`agents/chief_bond_strategist.py`, this platform's established department
for yield data, rather than being re-implemented as Macro factors.

`register_macro_data_sources(manager, fred_api_key)` is a new shared
helper (in `agents/chief_macro_officer.py`) that registers all 16 series
in one call — extracted specifically because three separate callers
(`scripts/demo_agents.py`, `scripts/run_daily_cycle.py`, the dashboard's
Department Reports page) all needed the identical 16-line registration
block; repeating it three times would have been exactly the kind of
copy-paste this codebase's conventions avoid.

## Dashboard

`dashboard/dashboard_utils.py`'s `render_agent_report()` gained a factor
breakdown table (via `st.dataframe`) shown whenever a report has one — a
small, natural first step toward the "hedge fund research terminal" look
the full spec asks for, without building the complete redesigned layout
(explicitly deferred per the scoping conversation). Verified with a real,
populated `FundamentalFactor` list driven through
`streamlit.testing.v1.AppTest.from_string` — not just assumed to work,
since every OTHER dashboard test runs with no network access in this
environment, meaning `factor_breakdown` is always empty in those tests and
would never have actually exercised the new pandas/dataframe code path.
This is the same class of gap (an untested render path) a real `NameError`
was caught in during the Trade Decision Engine integration review.

## Chief Commodity Fundamentals Officer — the second category

Per an explicit follow-up decision, "Commodity Fundamentals" is now built
as its own category, using the exact same `score_category()` engine — no
new aggregation logic was needed, proving the engine genuinely generalizes
beyond Macro as intended.

**Architecturally distinct from Chief Commodity Analyst.** The spec treats
COT positioning and Commodity Fundamentals as two separate sections, and
this platform now reflects that as two separate departments contributing
to the same commodity's synthesis:
- `agents/chief_commodity_analyst.py` (existing, Phase 3) — COT/speculative
  positioning, weighted 0.4 in `ChiefStrategyOfficer` (supporting-only,
  per `docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md`)
- `agents/chief_commodity_fundamentals_officer.py` (new) — real supply/
  demand data, defaults to the normal 1.0 weight (a fundamental desk, not
  COT) — no new entry needed in `DEFAULT_DEPARTMENT_WEIGHTS`, since
  unlisted departments already default to 1.0

**Honest scope: only energy commodities have real data right now.** Of the
spec's full Commodity Fundamentals wishlist (Supply, Demand, Inventories,
Mine Production, Central Bank Buying, ETF Flows, Jewellery Demand,
Industrial Demand, OPEC, Weather, Shipping, Export/Import Data,
Seasonality, Storage Levels, Cost of Production), only inventory/storage
data has a genuine free, structured, live source: the U.S. Energy
Information Administration's free public API
(`connectors/eia_connector.py`, same free-registration pattern as FRED).
`agents/chief_commodity_fundamentals_officer.py`'s `COMMODITY_FACTOR_SPECS`
currently covers exactly two commodities — Crude Oil (EIA weekly petroleum
stocks) and Natural Gas (EIA weekly storage) — reusing
`agents.trend_scoring.series_trend_score` directly, since `EiaConnector`
returns the same `{"latest_value", "latest_date", "history": [...]}` shape
`FredConnector` does.

**Every other commodity — Gold, Silver, Copper, Platinum, Palladium, and
every agricultural commodity — has NO configured factors**, and per an
explicit later decision, still shows up in the watchlist/dashboard WITH
the "Commodity Fundamentals" department present (not silently omitted),
honestly reporting `bias=neutral`, `confidence=0`, `risk_level=HIGH`, and
a `data_gaps` entry that says exactly why ("No free Commodity Fundamentals
data source configured for 'Gold' yet") — never a fabricated reading.
This was a deliberate design choice: a UNIFORM two-department shape
(`commodity` + `commodity_fundamentals`) across every commodity in
`config/watchlist.py` is more transparent for a hedge-fund-terminal-style
view than having some commodities silently show one department and others
two, even though it means most commodities' Fundamentals department
currently has nothing to say. `score_category()`'s existing empty-list
handling (from the Macro build) made this safe to do without any new code
— the honest degradation behavior was already built in.

**A real naming mismatch was caught and fixed during integration.**
`config/cftc_markets.py` (this platform's CFTC positioning data, built in
Phase 3) uses `"WTI Crude Oil"` as its display name, while this new
module's own tests/demo/dashboard code were written using the shorter
`"Crude Oil"`. Wiring the watchlist (which uses the CFTC naming
convention) surfaced the mismatch immediately — verified by actually
checking, not assumed. Rather than renaming either existing caller's
convention (which would have broken whichever one didn't get renamed),
both `COMMODITY_FACTOR_SPECS` and `EIA_ROUTE_SPECS` alias `"WTI Crude Oil"`
to the identical entry as `"Crude Oil"`, with two dedicated regression
tests (`test_wti_crude_oil_alias_resolves_to_the_same_factors_as_crude_oil`,
`test_register_commodity_fundamentals_sources_works_with_wti_alias`)
proving both names work identically.

`register_commodity_fundamentals_sources(manager, commodity, eia_api_key)`
is a shared registration helper (mirroring Macro's
`register_macro_data_sources`) — one canonical place for the EIA
route/facets mapping, used identically by `scripts/demo_commodity_fundamentals.py`,
`scripts/run_daily_cycle.py`, and the dashboard's Department Reports page,
rather than three separate copies of the same route strings.

## Testing

- `tests/test_weighted_stats.py` — 7 tests for the extracted shared math
- `tests/test_fundamental_scoring_engine.py` — 9 tests for `score_category()`
  (empty input, all-zero-confidence, importance-weight dominance,
  agreement vs. sharp disagreement, exclusion of zero-confidence factors)
- `tests/test_market_regime.py` — 13 tests for regime classification and
  weight adjustment (including that an empty FOMC list never fabricates
  a meeting)
- `tests/test_chief_macro_officer.py` — fully rewritten for the 16-factor
  engine (7 tests: bullish/bearish regimes, factor metadata correctness,
  degraded-coverage risk escalation, zero-data neutral/high-risk, evidence
  generation, disagreement handling)
- `tests/test_eia_connector.py` — 8 tests for the new EIA connector
  (history parsing, missing API key, empty/null rows, facet encoding)
- `tests/test_chief_commodity_fundamentals_officer.py` — 8 tests (bullish/
  bearish per-commodity readings, honest empty-factor-list behavior for
  unconfigured commodities, missing-data gaps, independent per-commodity
  instances, factor metadata, and the two WTI Crude Oil alias regression
  tests described above)
- `tests/test_dashboard_pages.py` — 2 new tests: the factor-breakdown
  table with real populated data, and a dedicated click-through of the
  Chief Commodity Fundamentals Officer selection (the existing generic
  "click the first button" test only ever exercised Chief Macro Officer,
  the selectbox's default — verified directly rather than assumed)
- 383 tests total, all passing; `scripts/demo_commodity_fundamentals.py`
  and `scripts/run_daily_cycle.py` (the full daily watchlist — all 33
  entries, every commodity showing exactly 2 departments) both re-run
  live to confirm end-to-end behavior, including that Gold and every
  other unconfigured commodity degrade honestly rather than crashing

## What's next (not yet built)

- Sentiment, Risk, Seasonality categories on this same `score_category()`
  engine (Macro and Commodity Fundamentals are done)
- Broadening Commodity Fundamentals beyond energy — metals (mine
  production, central bank buying, jewellery/industrial demand) and
  agriculture (USDA/WASDE crop data) would need new connectors this
  platform doesn't have yet; no free source currently identified for the
  metals side, USDA has a free API that could be a natural next connector
- The full "hedge fund research terminal" dashboard redesign (Market
  Overview header, Final Investment Committee table, etc.) — this phase
  only added a factor table to the existing Department Reports page
- The "Explain Every Decision" auto-explanation generator (why each
  factor is bullish/bearish, which had the greatest influence, which
  conflicted, strongest risks, what could invalidate the thesis) —
  deliberately deferred to its own phase rather than bolted on hastily
  alongside a 16-factor Macro expansion; this is genuinely a
  Chief-Strategy-Officer-level synthesis feature that deserves focused
  attention
- Wiring `agents/market_regime.py`'s weight adjustment into
  `ChiefStrategyOfficer`'s actual department-weighting logic (built and
  tested standalone in this phase; the integration point is straightforward
  once more categories exist to make its effect visible)

## Update: Commodity Fundamentals category (second category on this engine)

`agents/chief_commodity_fundamentals_officer.py` — a new
`ChiefCommodityFundamentalsOfficer`, instantiated per-commodity (same
pattern as `agents.positioning_agent_base.PositioningAgent`), using
`score_category()` exactly like Chief Macro Officer.

**Honest scope, applied identically to the Macro decision**: of the full
spec's Commodity Fundamentals wishlist (Supply, Demand, Inventories, Mine
Production, Central Bank Buying, ETF Flows, Jewellery Demand, Industrial
Demand, OPEC, Weather, Shipping, Export Data, Import Data, Seasonality,
Storage Levels, Cost of Production), only **inventory/storage data** has a
genuine free, structured, live source: the U.S. Energy Information
Administration's free public API (new `connectors/eia_connector.py`,
same "free key, paste into .env" pattern as FRED). Everything else in that
list is simply absent — not stubbed, not faked.

This means the category currently only has real content for **energy
commodities** (Crude Oil inventories, Natural Gas storage). For every
other commodity (Gold, Silver, Copper, all agricultural commodities), this
department has an empty factor list, and correctly reports
`bias=NEUTRAL`, `confidence=0.0`, `risk_level=HIGH`, with a data gap
explicitly stating "No free Commodity Fundamentals data source configured
for '<commodity>' yet" — the same honest degradation contract every other
missing-data case in this platform follows, never a fabricated reading.

`connectors/eia_connector.py` carries the same caveat already established
for `config/cftc_markets.py` and `config/sp500_tickers.py`: its exact
route/facet values (e.g. `"petroleum/stoc/wstk"`, `{"product": ["EPC0"]}`)
are a best-effort reading of EIA's v2 API structure, not verified against
a live query from this development environment (no network access here).
A wrong route/facet fails safely — `DataSourceError`, handled exactly like
any other connector failure — it does not silently return wrong data.
Verify against https://www.eia.gov/opendata/browser/ before relying on it.

**Per-commodity department weighting confirms the spec's intent
automatically**: `ChiefCommodityFundamentalsOfficer` isn't listed in
`ChiefStrategyOfficer.DEFAULT_DEPARTMENT_WEIGHTS`, so it gets the default
1.0 weight — the same as every other fundamental desk, and 2.5x
`ChiefCommodityAnalyst`'s COT-based 0.4 weight. No new weighting code was
needed; this fell out naturally from the department-weighting mechanism
already built for the Commercial Traders removal.

New `scripts/demo_commodity_fundamentals.py` runs both departments for
Crude Oil side by side plus the resulting `ChiefStrategyOfficer` synthesis
(and separately shows Gold's honest empty-category result) — verified
twice: once live in this network-isolated sandbox (correctly shows
missing-data degradation), and once with mocked bullish EIA data proving
the full bullish path through Fundamentals → Strategy Officer synthesis
→ `execution_readiness: high_conviction` actually works end to end.

14 new tests: 8 for `EiaConnector` (HTTP mocked, including a defensive
newest-first sort check and null-value handling), 6 for
`ChiefCommodityFundamentalsOfficer` (bullish/bearish scenarios, the
unconfigured-commodity honest-neutral case, missing-data gaps,
per-instance independence, factor metadata). 380 tests total.

## Update: wired into the dashboard, daily cycle, and watchlist

The above established the category and its tests; this pass connected it
to every place a real user actually touches the platform, following the
same "extract a shared registration helper rather than repeat it" pattern
used for `agents.chief_macro_officer.register_macro_data_sources`:

- **`register_commodity_fundamentals_sources(manager, commodity, eia_api_key)`**
  — new shared helper in `agents/chief_commodity_fundamentals_officer.py`,
  alongside a new `EIA_ROUTE_SPECS` mapping (commodity, factor) → (EIA
  route, facets). Before this, the demo script hardcoded its own copy of
  the route/facets inline — a second caller (the dashboard) needing the
  identical values was the trigger to extract them into one canonical
  source, consistent with this codebase's own "extract on 2nd/3rd
  consumer" convention. `scripts/demo_commodity_fundamentals.py` was
  simplified to use this helper instead of its original inline registration.
- **Dashboard** (`dashboard/pages/2_Department_Reports.py`) — new "Chief
  Commodity Fundamentals Officer" option, using the shared helper.
- **`scripts/run_daily_cycle.py`** — new `_run_commodity_fundamentals`
  runner, registered in `DEPARTMENT_RUNNERS["commodity_fundamentals"]`.
- **`config/watchlist.py`** — the daily watchlist adds a
  `commodity_fundamentals` department entry for EVERY commodity in
  `COMMODITY_FUTURES_MARKETS`, uniformly — not conditionally scoped to only
  Crude Oil/Natural Gas. This mirrors the same precedent already set by
  the FX/commodity COT entries elsewhere in this same file (every market
  gets a `"commodity"`/`"fx"` entry regardless of whether that specific
  market's CFTC name will actually resolve — `scripts/verify_watchlist_markets.py`
  exists precisely because some might not). `ChiefCommodityFundamentalsOfficer`'s
  existing empty-factor-list handling (built for the Macro category, reused
  here with zero new code) makes uniform registration safe: for every
  commodity without configured factors, the department runs, finds nothing
  to score, and honestly reports `bias=neutral`, `confidence=0`,
  `risk_level=HIGH` with an explicit data-gap message — never a crash,
  never a fabricated reading. A uniform department count across every
  watchlist entry was judged more transparent for a hedge-fund-terminal-
  style view than a per-commodity-varying shape, at the cost of some
  honest "nothing to report" no-op runs for commodities without free
  fundamentals data yet.

**A real naming mismatch was caught and fixed while wiring the watchlist**:
`config/cftc_markets.py` (CFTC's own report language) calls this commodity
`"WTI Crude Oil"`, while `chief_commodity_fundamentals_officer.py`'s own
tests/demo/dashboard code all used the shorter `"Crude Oil"`. Without a
fix, `ChiefCommodityFundamentalsOfficer(manager, commodity="WTI Crude Oil")`
(what the watchlist actually instantiates) would have silently found zero
configured factors for crude oil in the scheduled cycle, even though real
factors exist under the `"Crude Oil"` name — a genuine functional gap, not
just a cosmetic one, and one that direct verification caught (an isolated
check of `COMMODITY_FACTOR_SPECS` showed only `"Crude Oil"`/`"Natural Gas"`
as keys; a fresh check of `WATCHLIST_DAILY` against real commodity names
surfaced the mismatch immediately). Fixed by aliasing both
`COMMODITY_FACTOR_SPECS["WTI Crude Oil"]` and
`EIA_ROUTE_SPECS[("WTI Crude Oil", ...)]` to the exact same values as
their `"Crude Oil"` counterparts, rather than renaming either existing
caller's convention and risking breaking it. Two regression tests
(`test_wti_crude_oil_alias_resolves_to_the_same_factors_as_crude_oil`,
`test_register_commodity_fundamentals_sources_works_with_wti_alias`) lock
this in.

Verified end-to-end after wiring: `scripts/demo_commodity_fundamentals.py`
and a full run of `scripts/run_daily_cycle.py` (every commodity in the
watchlist, ~19 entries) both re-run live — every commodity correctly shows
2 contributing departments (`commodity` + `commodity_fundamentals`),
consistent with the uniform design above, with no crashes anywhere. The
dashboard's new department option was verified with a dedicated `AppTest`
interaction test (selecting it from the dropdown and clicking Run), not
assumed to work just because the page renders — the same discipline
already applied to the Institutional Relationship Engine's
execution-readiness display and the Trade Decision Engine's crash-bug fix.

**383 tests total.**

## Still not yet built

- Sentiment, Risk, Seasonality categories on this same `score_category()` engine
- The full "hedge fund research terminal" dashboard redesign
- The "Explain Every Decision" auto-explanation generator
- Wiring `agents/market_regime.py`'s dynamic weighting into
  `ChiefStrategyOfficer`'s actual department-weighting logic
- Non-energy Commodity Fundamentals (Gold/Silver/Copper/agriculture) —
  blocked on finding a genuine free live data source; not something to
  build until one exists
