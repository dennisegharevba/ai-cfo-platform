# AI Chief Fundamental Officer Platform

An institutional-grade, multi-agent AI research platform that replicates the
workflow of an institutional trading research department — across
commodities, equities, indices, ETFs, futures, forex, bonds, and crypto.

**This is not a trading bot.** It never places trades. It produces
research, probability-based directional bias, and gated alerts (Telegram +
dashboard) for a human to act on.

Built in fully working, tested, documented phases. All 11 phases on the
original roadmap are complete. The platform's main scoring pipeline now
runs 14 active Chief Officers (Chief Technical Officer was later fully
removed per user request — the platform now scores purely on
fundamentals, macro, and global news/sentiment; see
[`docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md`](docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md)).
See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full history.

## Phase 1: Data Integrity & Refresh Manager

The mandatory foundation every later agent depends on. No agent in this
platform is permitted to consume data that hasn't passed through it.

- Timestamps and quality-scores every dataset (0-100, fully explainable)
- Fails over to backup sources automatically
- Blocks usage of stale, unvalidated, or missing data — never fabricates
- Logs every refresh for audit
- Ships with three real, free connectors: FRED (macro), CFTC COT
  (positioning), Yahoo Finance (prices)

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Phase 2 (current): Chief Macro Officer + Chief Bond Strategist

The first two analytical agents, and the template every remaining Chief
Officer will follow.

- `BaseAgent` structurally enforces the data-integrity rule: an agent can
  never see a dataset that failed `is_usable()` — it's recorded as a
  `data_gap` and excluded before the agent's own logic ever runs
- Shared `AgentReport` output model (bias, confidence, risk, catalysts,
  risks, evidence, data_gaps) — every future officer reports in this same shape
- Chief Macro Officer: CPI + unemployment trend → growth/inflation regime bias
- Chief Bond Strategist: 10Y/2Y yield trend → bond price bias, plus yield
  curve inversion risk flagging

See [`docs/ARCHITECTURE_PHASE2.md`](docs/ARCHITECTURE_PHASE2.md) for the full design.

## Phase 3: Chief Commodity Analyst + Chief FX Analyst

Per-market positioning agents, built on a new shared `PositioningAgent` base.

- One agent instance per market (e.g. `ChiefCommodityAnalyst(manager, cot_key="COT_GOLD")`)
  — each is tied to a specific CFTC COT dataset key
- `CotConnector` extended to fetch multi-week positioning history (not just
  the latest snapshot), so agents can score positioning *trend*
- Blends **speculative (non-commercial) and commercial** positioning trend
  (60%/40%), rather than speculative alone — the two answer different
  questions (trend-following crowd behavior vs. real hedging exposure), and
  when they diverge meaningfully that's flagged as its own elevated-risk
  signal (a classic "trend nearing exhaustion" warning)
- Flags "crowded" speculative long/short positioning (>40% of open interest)
  as an elevated-risk signal, independent of the directional bias itself
- Chief Commodity Analyst and Chief FX Analyst are currently ~2 lines each —
  all shared logic lives in `PositioningAgent`; they'll diverge once
  commodity-specific (USDA/EIA/weather) and FX-specific (rate differentials,
  DXY) data get added in later phases

See [`docs/ARCHITECTURE_PHASE3.md`](docs/ARCHITECTURE_PHASE3.md) for the full design.

## Phase 4 (current): Chief Equity Analyst + Chief Cryptocurrency Analyst

- Chief Equity Analyst: EPS + revenue trend per ticker, via a new free SEC
  EDGAR connector (10-Q/10-K filings only, no API key — just a descriptive
  User-Agent)
- Chief Cryptocurrency Analyst: funding rate (60%) + open interest trend
  (40%) per symbol, via a new free Binance futures connector; flags extreme
  funding rates as a crowded long/short trade
- Extracted `agents/trend_scoring.py` as a shared module once a third agent
  needed the same "trend from a fetched window" scoring logic

See [`docs/ARCHITECTURE_PHASE4.md`](docs/ARCHITECTURE_PHASE4.md) for the full design.

## Phase 5: Chief Sentiment Officer (originally + Chief Technical Officer)

- Chief Sentiment Officer: free news-RSS headline sentiment (keyword-based,
  fully explainable — no ML black box), optionally blended with the same
  CFTC COT dataset a Chief Commodity/FX Analyst already reads, reinterpreted
  as a crowd-sentiment signal

**Chief Technical Officer** (RSI/MACD/SMA-based) was originally built here
too, but was later **fully removed** from the platform's main scoring
pipeline per user request — the platform now scores purely on
fundamentals, macro, and global news/sentiment. See
[`docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md`](docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md).
The separate Trade Decision Engine (below) still has its own independent
technical/momentum logic by explicit user choice — it never depended on
this department's code.

See [`docs/ARCHITECTURE_PHASE5.md`](docs/ARCHITECTURE_PHASE5.md) for the full design.

## Phase 6 (current): Chief Risk Officer

The first genuinely different agent shape — analyzes a whole **portfolio**
of positions rather than one asset/theme.

- New `PortfolioAgent` base class (parallel to `BaseAgent`, same
  data-integrity contract, keyed by symbol instead of a fixed dataset list)
- New `Portfolio`/`Position` models
- Concentration, portfolio volatility, historical VaR (95%), max drawdown,
  and average pairwise correlation — all pure-Python, no numpy
- Deliberately non-directional: `bias`/`bias_score` stay neutral/0 for this
  agent; the actual assessment lives in `risk_level` and the evidence/risks
  lists (the Risk desk says how risky, not which way)
- No new connector — reuses Phase 5's Yahoo Finance history connector
  across every position in the portfolio

See [`docs/ARCHITECTURE_PHASE6.md`](docs/ARCHITECTURE_PHASE6.md) for the full design.

## Phase 7 (current): Chief Strategy Officer

The synthesis layer — where all 9 agents built so far finally work
together instead of sitting side by side.

- A third architectural shape: fetches no data itself, only consumes
  `AgentReport`s other agents already produced
- Confidence-weighted synthesis (`department_weight × confidence/100`),
  with sentiment/technical weighted below the fundamental desks by default
  (configurable)
- Genuine disagreement resolution: a weighted standard deviation across
  departments' bias scores both pulls the overall score toward neutral AND
  separately docks confidence — so "everyone agrees it's neutral" and
  "departments are split 50/50" don't get reported with the same confidence
- The Chief Risk Officer's report is handled specially: excluded from the
  directional math (it's always neutral by design) but still escalates the
  final risk level and contributes its risks to the output
- Produces Overall Market Score, Confidence Score, Risk Level, Directional
  Bias, Trade Thesis, Catalysts/Risks, qualitative Invalidation Notes, and
  an Investment Committee Summary — all via deterministic templating, no
  LLM call

See [`docs/ARCHITECTURE_PHASE7.md`](docs/ARCHITECTURE_PHASE7.md) for the full design.

## Phase 8 (current): Chief Learning Officer

The platform's memory — a fourth architectural shape with no `analyze()`
method at all.

- New SQLite-based `database/report_store.py` (free, Python stdlib only,
  zero external server) — stores every `AgentReport` and `StrategyReport`
  ever produced, plus manually-recorded outcomes
- `department_performance_summary()` — report counts, average confidence,
  bias distribution, and how often a department was working with degraded
  data, per department
- `strategy_accuracy_summary()` — win rate and average realized return
  across every judged strategy report; unjudged theses are excluded rather
  than counted as losses
- Outcomes are recorded manually/after the fact (never computed from a
  trade — this platform never places one), consistent with the rest of the
  platform's "never fabricate a result you don't actually have" principle

See [`docs/ARCHITECTURE_PHASE8.md`](docs/ARCHITECTURE_PHASE8.md) for the full design.

## Phase 9: Chief Execution Officer — the twelfth and final officer from the original spec

The final officer, and a gate rather than an analyst.

- Reads a `StrategyReport` (Phase 7) and only alerts when confidence, bias
  strength, risk level, and data coverage ALL clear configurable thresholds
  — every blocking reason is independently checked and reported, not just
  the first one found
- New free `TelegramAlerter` (`telegram/telegram_alerter.py`) — no cost
  beyond creating a bot via @BotFather
- A failed send is recorded on the decision (`send_error`), never silently
  swallowed — consistent with the "never fail silently" principle used
  throughout the data-integrity layer since Phase 1
- `evaluate()` is pure (no side effects) and separable from `process()`
  (which actually sends) — useful for a future dashboard to show "would
  this have alerted?" without risking a real message

See [`docs/ARCHITECTURE_PHASE9.md`](docs/ARCHITECTURE_PHASE9.md) for the full design.

## Phase 10 (current): Streamlit Dashboard

A real, working multi-page dashboard — not a mockup — over everything
built in Phases 1-9.

- **Data Health** — live status of every registered data source
- **Department Reports** — run any single-asset Chief Officer live
- **Strategy Synthesis** — Chief Strategy Officer's cross-department resolution
- **Risk Officer** — interactive portfolio builder + live risk analysis
- **Performance & Learning** — real persistent history + analytics
- **Alerts & Execution** — adjustable gating thresholds + a real (safety-railed) Telegram send

Verified with Streamlit's own `AppTest` harness — every page is actually
executed (not just curl'd) and its primary button clicked, with no network
access, matching CI conditions exactly.

See [`docs/ARCHITECTURE_PHASE10.md`](docs/ARCHITECTURE_PHASE10.md) for the full design.

## Phase 11 (current, final): Scheduled Automation — all 11 phases complete

The pipeline now runs unattended, on a schedule, instead of via manual
demo scripts or dashboard clicks.

- New `config/watchlist.py` — split into a **daily** watchlist (macro, all
  major CFTC FX/commodity futures, crypto, sentiment) and a **weekly**
  watchlist (~357 large-cap equities) on separate GitHub Actions schedules,
  since fundamentals don't change daily
- New `connectors/sec_ticker_lookup.py` — resolves any ticker's SEC CIK
  automatically from one free bulk mapping file, instead of requiring a
  hand-entered CIK per company (what made broad equity coverage practical)
- New `scripts/run_daily_cycle.py` — runs every watchlist entry through
  its configured departments, synthesizes, persists, and evaluates for
  alerting; one asset's failure is isolated and logged, never stops the
  rest of the cycle
- New `.github/workflows/scheduled_run.yml` (daily) and
  `scheduled_run_equities.yml` (weekly) — cron + manual trigger,
  credentials from GitHub Actions secrets, database persisted across
  ephemeral runners via `actions/cache`
- `scripts/verify_watchlist_markets.py` — a diagnostic tool to check every
  CFTC market name and ticker against the real APIs (both lists are
  best-effort/point-in-time, honestly flagged as such — see
  `docs/ARCHITECTURE_PHASE11.md`)

See [`docs/ARCHITECTURE_PHASE11.md`](docs/ARCHITECTURE_PHASE11.md) for the full design.

**244 passing tests total, CI on every push.**

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add your free FRED API key + SEC_USER_AGENT (+ Telegram credentials, optional)

# Run the dashboard:
streamlit run dashboard/Home.py

# Run the automated research cycle manually:
python scripts/run_daily_cycle.py                    # daily watchlist (macro/FX/commodities/crypto/sentiment)
python scripts/run_daily_cycle.py --watchlist weekly  # weekly watchlist (~357 equities)

# Check the best-effort CFTC market names / tickers against the real APIs:
python scripts/verify_watchlist_markets.py

# Or run any individual phase's demo script:
python scripts/demo_refresh.py
python scripts/demo_agents.py
python scripts/demo_commodity_fx_agents.py
python scripts/demo_equity_crypto_agents.py
python scripts/demo_sentiment_agent.py
python scripts/demo_risk_officer.py
python scripts/demo_strategy_officer.py
python scripts/demo_learning_officer.py
python scripts/demo_execution_officer.py

pytest tests/ -v
```

## Setting up scheduled automation on your own repo

1. Go to your repo's **Settings → Secrets and variables → Actions**
2. Add secrets: `FRED_API_KEY`, `SEC_USER_AGENT`, and (optionally)
   `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
3. Two workflows run automatically on their own schedules, or can be
   triggered manually from the **Actions** tab via "Run workflow":
   - `.github/workflows/scheduled_run.yml` — daily (weekdays), the fast
     watchlist (macro/FX/commodities/crypto/sentiment)
   - `.github/workflows/scheduled_run_equities.yml` — weekly (Sundays),
     the ~357-ticker equity sweep

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) and
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for details.

## Repository layout

```
core/          Data Integrity & Refresh Manager (Phase 1 — built)
connectors/    FRED, CFTC COT, Yahoo (quote + history), SEC EDGAR, Binance, News RSS
agents/        14 active Chief Officers + BaseAgent/PortfolioAgent patterns
               (Chief Technical Officer was later removed — see
               docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md)
models/        AgentReport, Portfolio, Position, StrategyReport, ExecutionDecision
database/      SQLite persistence: report_store.py, schema.py (Phase 8 — built)
telegram/      TelegramAlerter — free Bot API wrapper (Phase 9 — built)
dashboard/     Multi-page Streamlit app: Home.py + pages/ (Phase 10 — built)
config/        Settings, refresh intervals, watchlist.py (Phase 11 — built)
tests/         715 passing tests, network-independent (fake sources, mocked HTTP, AppTest)
scripts/       demo_*.py + run_daily_cycle.py (the production entry point)
docs/          Architecture (Phases 1-11), installation, configuration, roadmap
data/          Reserved: local caches/fixtures (not needed yet)
utils/         Shared logging setup
```

## This project is now complete

All 11 phases on the original roadmap are built, tested, and documented:
data integrity, the Chief Officer departments, a dashboard, and scheduled
automation. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full history
and [`docs/ARCHITECTURE_PHASE11.md`](docs/ARCHITECTURE_PHASE11.md) for
natural next steps beyond the original spec.

## Addition: Institutional Trade Decision Engine

A substantial addition on top of the 11-phase build, from a separate spec.
Runs alongside the Chief Strategy Officer rather than replacing it — same
underlying department reports, a different way of using them:

- **Chief Trade Decision Officer** (`agents/chief_trade_decision_officer.py`)
  keeps Fundamental (40%), Technical (40%), and Risk (20%) scores
  independently visible throughout, gating any "enter now" recommendation
  on an 8-point entry-confirmation checklist between them — never on one
  blended score alone
- **Asset Risk Officer** — per-asset volatility, ATR-based stop distance,
  and event/news risk, mirroring the portfolio-level Chief Risk Officer's
  approach at the single-asset level
- **Trade Lifecycle Officer** — monitors a user-declared open trade (never
  one the platform places itself) and rates its ongoing health
- New dashboard page: **Trade Decision Engine**

One real bug was found and fixed during integration review — a dashboard
page crash caught by actually executing it with Streamlit's `AppTest`
harness, not by trusting the accompanying "all tests pass" claim. Full
account in
[`docs/ARCHITECTURE_TRADE_DECISION_ENGINE.md`](docs/ARCHITECTURE_TRADE_DECISION_ENGINE.md),
including honestly-carried-over limitations (no cross-asset correlation
yet, technical entry-confirmation proxied from existing indicators rather
than dedicated breakout/volume detectors).

## Addition: Institutional Relationship Engine

An upgrade to the Chief Commodity/FX Analyst and Chief Strategy Officer,
implementing an explicit philosophy: Commercial Hedgers and Large
Speculators are never forced to "pick a winner." Instead their
relationship is classified, and that classification adjusts confidence,
never direction.

- **Alignment classification** (`agents/institutional_relationship.py`) —
  Full Alignment / Mild Divergence / Strong Divergence between commercial
  and speculative positioning, each with its own confidence adjustment
  (+15 / -10 / -25, the exact values from the spec)
- **Execution Readiness** — four tiers (🟢 High Conviction / 🟡
  Conditional Opportunity / 🔵 Watchlist / 🔴 No Trade), computed at the
  Chief Strategy Officer level since it needs to know whether the Chief
  Technical Officer's own read confirms the synthesized bias
- **Institutional Commentary** — a deterministic "why" paragraph on every
  `StrategyReport`, no LLM call, in the spec's own voice
- A real on-disk-database migration path for the two new `StrategyReport`
  fields, proven against a database file built with the exact pre-upgrade
  schema

Full account, including what the spec asked for that's honestly NOT
built (adaptive/self-learning weights and thresholds — a real backtesting
system of its own, not a natural extension of what's here), in
[`docs/ARCHITECTURE_INSTITUTIONAL_RELATIONSHIP_ENGINE.md`](docs/ARCHITECTURE_INSTITUTIONAL_RELATIONSHIP_ENGINE.md).

**318 passing tests total.**

## Update: Chief Technical Officer removed

Per explicit user request, Chief Technical Officer was **fully deleted**
(code and tests, not just disabled) from the platform's main scoring
pipeline. The main research pipeline (Chief Strategy Officer's synthesis)
now scores purely on fundamentals, macro, and global news/sentiment — no
technical/price-action department is part of it anymore.
`classify_execution_readiness()` no longer gates its High Conviction tier
on a technical confirmation signal, since none exists to provide one.

The separate Trade Decision Engine (above) was deliberately **left
unchanged** — by explicit user choice, it keeps its own independent
Fundamental/Technical/Risk scoring for trade entry timing, which never
depended on the deleted `ChiefTechnicalOfficer` class in the first place
(verified by checking every import before deleting anything).

Full account in
[`docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md`](docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md).

**311 passing tests total** (down from 318 — the dedicated test file for
the now-deleted agent was removed along with it).

## Update: Commercial Traders removed as a directional COT input

Per an explicit later decision, Commercial Traders (hedgers) no longer
influence bias, confidence, or the overall market score anywhere in the
platform. Primary emphasis is now on Non-Commercial Traders (Large
Speculators) — more representative of trend-following institutional
capital that drives medium- to long-term price movements.

- **`agents/speculative_positioning_analysis.py`** — new week-over-week
  momentum tracking, a percentile rank of current positioning against its
  own recent history (with an honest "within-fetched-window, not
  multi-year" caveat), and a continuation/reversal classification
- New confidence model: base 55, +15 for momentum confirming the broader
  trend, -15 if it opposes it, -10 if positioning is at a historical
  extreme — every constant named, every combination covered by a
  hand-verified test
- **Chief Strategy Officer now weights COT departments at 0.4** vs. the
  fundamental desks' 1.0 default — proven with a worked example showing
  the re-weighting genuinely flips which side wins a disagreement, not
  just softens it
- Commercial data can still be shown as clearly-labeled informational
  context via `ENABLE_COMMERCIAL_POSITIONING_DISPLAY` (default off), but
  even when enabled it never touches scoring — proven with a test using
  deliberately opposite commercial data producing byte-identical scores

Full account, including what was deliberately left alone (the separate
Trade Decision Engine's own commercial/speculative divergence check), in
[`docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md`](docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md).

**332 passing tests total.**

## Update: Institutional Fundamental Scoring Engine (Phase 1 — Macro)

The Chief Fundamental Officer engine no longer produces a market bias
primarily from COT. Every major macroeconomic factor is now evaluated
INDEPENDENTLY — current/previous/forecast/bias/1-10 importance weight/
confidence/timestamp/source — before contributing to a category score.
Three scope-defining questions were confirmed before building: Technical
Confirmation stays out (Chief Technical Officer remains removed), factors
with no free live data source are skipped rather than faked, and this
first delivery covers Macro + the core engine (Commodity Fundamentals,
Sentiment, Risk, and Seasonality follow later on the same engine).

- **Chief Macro Officer now scores 16 real, free, FRED-backed factors**
  (CPI, Core CPI, PPI, Core PCE, GDP, Retail Sales, Unemployment, NFP,
  Average Hourly Earnings, JOLTS, Initial Claims, Dollar Index, Credit
  Spreads, Consumer Confidence, Housing Starts, Federal Debt) instead of
  just 2 — no new connector needed, all via the existing free `FredConnector`
- New **`agents/fundamental_scoring_engine.py`** — a generic
  `score_category()` step reusable by every future category, built on a
  newly-shared **`agents/weighted_stats.py`** (extracted from
  `ChiefStrategyOfficer` rather than duplicated)
- New **`agents/market_regime.py`** — honestly rule-based (not
  self-learning) dynamic weighting: FOMC weeks boost Macro weight,
  earnings season boosts Equity Fundamentals weight. The FOMC calendar
  (`config/fomc_meeting_dates.py`) ships EMPTY rather than guessed —
  same "never fabricate a fact you can't verify" precedent as the CFTC
  market names and S&P 500 ticker list
- `AgentReport` gained an additive `factor_breakdown` field (defaults to
  `[]`) so every other department keeps working completely unchanged
- Dashboard's Department Reports page shows a live per-factor breakdown
  table — verified with real populated data via `AppTest.from_string`,
  since every other dashboard test runs offline and would never have
  actually exercised the new render path otherwise

Full account, including exactly what's deliberately NOT included yet
(PMIs, central bank text analysis, the full terminal dashboard redesign,
auto-generated explanations), in
[`docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md`](docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md).

A second category was added on this same engine:
**Chief Commodity Fundamentals Officer** — real, free, live inventory/
storage data (Crude Oil, Natural Gas) via a new EIA connector, weighted
1.0 (the fundamental-desk default) vs. Chief Commodity Analyst's
COT-based 0.4. Every other commodity (Gold, Silver, Copper, agriculture)
honestly reports an empty, zero-confidence category — no free structured
data source exists for those yet, so nothing is fabricated to fill the gap.

Wired into every real touchpoint via a shared
`register_commodity_fundamentals_sources()` helper: the dashboard's
Department Reports page, `scripts/run_daily_cycle.py`'s new
`commodity_fundamentals` department, and `config/watchlist.py`. Per an
explicit follow-up decision, EVERY commodity in the watchlist shows both
departments (`commodity` + `commodity_fundamentals`) uniformly — Gold,
Silver, and every agricultural commodity included — rather than only the
two with real configured data. Unconfigured commodities honestly report
`neutral`/`confidence=0`/`risk=HIGH` with an explicit data-gap message
naming the commodity, never a fabricated reading; verified live against
the full 33-entry daily watchlist. Wiring the watchlist also caught a
genuine naming mismatch — CFTC's own convention calls this commodity "WTI
Crude Oil" while this module's tests/demo used the shorter "Crude Oil" —
fixed via an explicit alias with two regression tests, rather than
silently leaving the scheduled cycle unable to find the configured
factors at all.

**383 passing tests total.**

## Update: Institutional Market Regime Filters + Precious Metals fundamentally backed by USD data

Two related upgrades:

1. **Gold, Silver, Platinum, and Palladium are now fundamentally backed**,
   not just COT alone — using the same US-Dollar-related fundamentals
   that drive USD itself (Real Yield, Dollar Index, Fed Funds Rate), on
   the reasoning that these metals are priced in dollars. These factors
   **reuse Chief Macro Officer's exact same FRED-backed dataset keys**
   rather than fetching the identical series a second time — proven with
   a dedicated test, not assumed. (Earlier in this same README, Gold was
   described as uniformly included in the watchlist but "honestly having
   nothing to say" — it now genuinely does.)
2. **Institutional Market Regime Filters** (`agents/institutional_market_regime.py`)
   — Federal Reserve Policy (real Fed Funds Rate trend, FRED), 10Y TIPS
   Real Yield, 10Y Treasury Yield, and VIX, all real and free via FRED,
   combined using the spec's exact weights (Macro 40% / Fed 20% / Real
   Yield 15% / Treasury 15% / VIX 10%) into a confidence-adjusting
   confirmation layer for Chief Macro Officer — reusing the Institutional
   Relationship Engine's existing alignment classifier (originally built
   for commercial/speculative COT, orphaned since that removal) rather
   than inventing a parallel mechanism. The regime **confirms or warns —
   it never overrides the Macro bias's direction**, per the spec's own
   explicit Trade Filter Rule; proven with a test showing the bias stays
   identical even under maximum regime disagreement.

A real dead-code bug (an unreachable "insufficient data" fallback) and a
real functional gap (precious metals needing Macro's registration
function called too, or they'd always show zero confidence in the real
scheduled cycle) were both found during my own review and fixed before
delivery — full account, including exactly what's honestly not modeled
(FOMC statement tone, Dot Plot, CME FedWatch — no free structured source
for any of them), in
[`docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md`](docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md).

**437 passing tests total.**

## Update: Seasonality, Sentiment, and Risk — the remaining categories complete

The Institutional Fundamental Scoring Engine now covers every category
from the original spec's Final Investment Committee table:

- **Seasonality** (`agents/chief_seasonality_officer.py`) — new. Real,
  well-documented historical seasonal patterns for Gold, WTI Crude Oil,
  Natural Gas, Corn, Wheat, Soybeans, S&P500, and NASDAQ100 (e.g. gold's
  historical strength around Indian wedding season, "sell in May" for US
  equities) — explicitly labeled as widely-cited market patterns, NOT a
  statistical backtest this platform computed. Architecturally distinct:
  it fetches no data at all (a pure calendar lookup), which means it kept
  producing genuinely correct scores even in this fully network-isolated
  sandbox — verified live, matching the documented table exactly.
- **Sentiment** — the existing Phase 5 Chief Sentiment Officer's real
  news-sentiment scoring now also populates the standard factor-breakdown
  format, added purely additively with the original, already-tested
  bias/confidence math left completely untouched — zero regression.
- **Risk** (`agents/chief_risk_fundamentals_officer.py`) — new per-asset
  volatility/drawdown, built entirely from existing, already-tested math
  (`agents/risk_calculations.py`) and the existing Yahoo Finance
  connector — no new calculation logic, no fabrication. Since "low
  volatility" is a claim about stability, not direction, it's routed
  through a newly-generalized `risk_reports` parameter on
  `ChiefStrategyOfficer` (extending the same bias-exclusion pattern
  already used for the portfolio-level Chief Risk Officer) — proven with
  a real end-to-end test through the actual scheduled-cycle code path,
  after finding and fixing a real integration gap where risk-type reports
  would otherwise have been silently folded into the directional average.

Full account, including what's honestly still not modeled and a real bug
found and fixed mid-edit (an orphaned test function from a bad
find-and-replace), in
[`docs/ARCHITECTURE_REMAINING_CATEGORIES.md`](docs/ARCHITECTURE_REMAINING_CATEGORIES.md).

**469 passing tests total.**

## Update: "Explain Every Decision" — the auto-explanation generator

Per the spec's explicit requirement, `ChiefStrategyOfficer.synthesize()`
now produces a `decision_explanation` field covering all five required
points in one deterministic paragraph (no LLM call, same as every other
narrative field in this platform):

- **Why each factor is bullish/bearish/neutral** — every contributing
  department's own read
- **Which had the greatest influence** — ranked by the exact same
  effective weight already used to compute the overall bias, not
  re-derived
- **Which conflicted with the final decision** — departments whose bias
  meaningfully opposed the overall direction
- **The strongest risks** and **what could invalidate the analysis** —
  reusing the platform's existing risk/invalidation-notes infrastructure

This was the natural next step after the six scoring categories: with
Macro, Commodity Fundamentals, COT, Sentiment, Seasonality, and Risk all
producing real detail, `ChiefStrategyOfficer` already had everything the
spec's explanation needs sitting in its own synthesis method — a small,
well-scoped addition, not a new subsystem. Verified live: re-running
`scripts/demo_strategy_officer.py` produced a genuinely coherent
explanation that correctly named the highest-weighted department, flagged
the one genuinely conflicting department, and matched its own underlying
data exactly.

Full account in
[`docs/ARCHITECTURE_DECISION_EXPLANATION.md`](docs/ARCHITECTURE_DECISION_EXPLANATION.md).

**476 passing tests total.**

## Update: "Institutional Research Terminal" dashboard redesign

Given creative latitude on the visual direction, the dashboard now has a
real, deliberate identity rather than default Streamlit styling:

- **Dark terminal aesthetic with an antique-gold accent** (`#C9A227`) —
  chosen specifically because this platform's own defining feature is
  precious-metals fundamentals (Gold/Silver/Platinum/Palladium backed by
  real USD data), not a generic AI-design cliché color
- **A signature reusable "bias gauge"** — a horizontal -100..+100 visual,
  color-graded bearish-to-bullish, drawn directly from the one value
  every single agent in this platform actually produces (`bias_score`),
  now appearing everywhere that score shows up: Department Reports,
  Strategy Synthesis, and the redesigned Home page
- **Home page redesigned into a live "Market Overview"** — surfaces
  whatever's actually been analyzed this session (grouped by asset, with
  the latest Strategy Synthesis front and center), instead of a static
  description of what the other pages do

A real bug was caught and fixed before shipping: the gauge's first draft
used Python object identity (`id()`) for its SVG gradient ID, which could
silently collide when the same score appeared twice on one page — fixed
with a proper UUID, locked in with a dedicated regression test. Full
account, including the honest design-process reasoning for every color
and layout choice, in
[`docs/ARCHITECTURE_DASHBOARD_REDESIGN.md`](docs/ARCHITECTURE_DASHBOARD_REDESIGN.md).

**478 passing tests total.**

## Update: Final Investment Committee table

`ChiefStrategyOfficer.synthesize()` now produces a `committee_table` and
`committee_recommendation` on every `StrategyReport`, matching the
original spec's exact example format:

```
Factor                    Bias      Weight    Confidence
Macro                     Bullish   30%       92%
...
Final Market Score: 82 / 100
Confidence: 91%
Overall Bias: Bullish
Investment Committee Recommendation: Long
```

Built entirely from data already computed for the "Explain Every
Decision" generator — the same real effective-weight figures that
actually produced the synthesis, normalized to percentages that sum to
~100%, not a separately-guessed approximation. The recommendation
deliberately reads "Long (research view)" rather than a bare "Long" —
this platform has never placed a trade in any phase, and this stays a
research conclusion label, never an execution instruction (locked in with
a dedicated test). Verified live: `scripts/demo_strategy_officer.py`'s
output now matches the spec's example table exactly.

Full account in
[`docs/ARCHITECTURE_INVESTMENT_COMMITTEE_TABLE.md`](docs/ARCHITECTURE_INVESTMENT_COMMITTEE_TABLE.md).

**487 passing tests total.**

## Update: risk_fundamentals extended to currency, equities, and crypto

Per an explicit request to extend real per-asset volatility/drawdown
coverage beyond commodities, `Chief Risk Fundamentals Officer` is now
wired into every asset class this platform covers:

- **Currency (FX)** — all 11 configured pairs, using Yahoo's FX ticker
  convention (`EURUSD=X`, `JPY=X`, etc. — best-effort, same caveat as
  every other "verify against a real source" mapping in this project)
- **Equities** — all ~357 tickers in the weekly watchlist. This
  deliberately reverses an earlier documented decision that excluded
  equities specifically to avoid the added weekly request volume
  (~350 more Yahoo Finance calls) — now accepted explicitly, per your
  request, not silently
- **Crypto** — BTC, using Yahoo's `BTC-USD` convention

No agent code changed — `ChiefRiskFundamentalsOfficer` and the daily
cycle's runner were already fully generic (any ticker works); this was
purely a watchlist config change. 6 new tests specifically lock in the
actual coverage counts (not just "the department resolves to a handler"),
so a future change can't silently narrow coverage back down without a
test failing. Verified live against the real daily cycle and a slice of
the weekly equity cycle.

Full account in
[`docs/ARCHITECTURE_REMAINING_CATEGORIES.md`](docs/ARCHITECTURE_REMAINING_CATEGORIES.md).

**493 passing tests total.**

## Update: four real bugs found and fixed in Strategy Synthesis + Trade Decision Engine

Found by actually reading the code end-to-end in response to a direct
question, not by routine testing:

1. **Strategy Synthesis dashboard never used the `risk_reports` split** —
   Chief Risk Fundamentals Officer's "how risky" reading was silently
   being folded into the directional bullish/bearish average. Fixed with
   a real regression test proving a bearish risk reading no longer moves
   the bias, only the risk level.
2. **Trade Decision Engine silently excluded newer departments** — Chief
   Commodity Fundamentals Officer, Chief Seasonality Officer, and Chief
   Risk Fundamentals Officer were all missing from its hardcoded
   department lists, built before those departments existed and never
   revisited.
3. **The most significant one: Technical Score has been silently stuck
   at neutral (50/100) since Chief Technical Officer was removed.** The
   Trade Decision Engine looked for a report literally named "Chief
   Technical Officer" — a department that can never exist again. This
   contradicts an earlier claim in this project's own documentation and
   was a real, undiscovered regression. Fixed with genuine live technical
   scoring (RSI + MACD + SMA trend, computed fresh from real Yahoo
   Finance price history) — no resurrected code, all built on this
   platform's existing tested indicator math.

Full account in
[`docs/ARCHITECTURE_TRADE_DECISION_TECHNICAL_FIX.md`](docs/ARCHITECTURE_TRADE_DECISION_TECHNICAL_FIX.md).

**513 passing tests total.**

## Update: three self-identified improvements, fixed

Following a direct self-assessment ("what can I improve on this
machine"), then a fact-check of every claim against the actual code
before acting on any of it:

- **Cycle health detection** (`agents/cycle_health.py`) — the platform's
  existing error handling only caught hard crashes. Given this platform's
  own "never crash, always degrade gracefully" philosophy, the more
  likely real failure mode is everything completing successfully while
  silently returning near-zero confidence everywhere (an expired API key,
  a blocked host). This distinguishes normal per-asset noise from a
  genuine systemic issue and flags it plainly. Verified live against this
  sandbox's own lack of network access — it correctly identified itself
  as systemically degraded, in real time.
- **Dynamic regime weighting — actually wired in.** `agents/market_regime.py`
  existed, fully tested, but had never been connected to
  `ChiefStrategyOfficer`. Now it is, with tests proving the exact same
  input produces a genuinely different outcome during an earnings-season
  month vs. a normal one — not just a cosmetic multiplier that never
  fires.
- **The three risk agents, finally documented together** — one doc now
  explains why `ChiefRiskOfficer`, `ChiefRiskFundamentalsOfficer`, and
  `ChiefAssetRiskOfficer` all exist and what each one is actually for.
- **Verification tooling extended** — `scripts/verify_watchlist_markets.py`
  now checks every FX/commodity/crypto Yahoo ticker and EIA route this
  platform has accumulated, not just CFTC names and equity tickers. This
  one genuinely needs to be run with real network access to mean
  anything — every check here reports "BAD" purely because this sandbox
  can't reach the internet at all.

Deliberately NOT attempted: real backtesting against historical data —
the single largest remaining gap, and one that deserves its own proper
scoping conversation rather than being rushed in alongside four smaller,
well-bounded fixes.

Full account, including a subtle test-fragility risk caught and
documented (not silently patched) along the way, in
[`docs/ARCHITECTURE_SELF_IMPROVEMENT_FIXES.md`](docs/ARCHITECTURE_SELF_IMPROVEMENT_FIXES.md).

**539 passing tests total.**

## Update: real backtesting — signal validation, not P&L simulation

This platform never places trades, so "backtesting" here means asking a
narrower, honest question: did more bullish historical readings actually
precede better subsequent price performance than bearish ones? The
correlation-validation approach quant researchers use to check a factor
before ever trading on it — not a simulated P&L.

The hard part solved first: **point-in-time correctness**.
`connectors/fred_historical.py` uses FRED's own vintage-query API
(`realtime_start`/`realtime_end`) to fetch what a series' value genuinely
was AS OF a historical date — not today's revised number. Using today's
revised CPI to test what Chief Macro Officer would have said in 2023 is a
classic look-ahead-bias mistake that would make the signal look smarter
than it could actually have been; this avoids it properly rather than
caveating it away.

`agents/backtest_engine.py` is signal-agnostic (Spearman rank correlation,
built on the platform's own existing `pearson_correlation` rather than a
new scipy dependency) and five real signals are wired into it via
`agents/backtest_signals.py`: Seasonality (zero point-in-time risk at
all) and four Institutional Market Regime components (VIX, Real Yield,
Treasury Yield, Fed Policy — all daily market-observed rates, never
meaningfully revised). Every signal wrapper reuses the exact scoring
function its live department already uses.

Four real mistakes were caught and fixed along the way, not glossed over
— including a floating-point test assertion, a synthetic price series
that mathematically went negative, two mis-judged threshold assertions,
and a genuine usability bug in the runnable script (conflating a display
name with a ticker symbol) caught only by actually running it live.

Deliberately still deferred: Macro's survey-revised factors (the hard
infrastructure exists, wiring all 10 factors in is real additional
scope), COT-based backtesting, and P&L/trade simulation (out of scope by
design). News Sentiment is permanently excluded — the RSS connector has
no historical archive to backtest against.

Full account in
[`docs/ARCHITECTURE_BACKTESTING.md`](docs/ARCHITECTURE_BACKTESTING.md).

**567 passing tests total.**

## Update: macro factor normalization recalibrated — found via your live FRED key

Once a real `FRED_API_KEY` was working, a live run of
`scripts/demo_agents.py` showed 7 of Chief Macro Officer's 16 factors
simultaneously clamped at the exact ±100 extreme — not plausible as
coincidence. Root cause: every factor shared the same 5% "maximally
bullish/bearish" threshold regardless of how naturally volatile that
specific series is, compounded by a fixed 5-observation fetch window that
spans a wildly different real time period depending on each series'
reporting frequency (5 weeks for Initial Jobless Claims, ~15 months for
GDP). Genuinely noisy series (Initial Claims, Housing Starts) and
naturally-compounding level series (GDP, Federal Debt) were structurally
biased to hit the clamp almost regardless of actual conditions.

Recalibrated per factor based on each series' well-documented real-world
characteristics — Initial Claims and Housing Starts widened the most
(known as the noisiest indicators in US economic data), GDP and Federal
Debt widened so only above-trend growth registers as extreme, PPI/JOLTS/
Consumer Confidence moderately widened. Every factor that was already
producing sensible, non-clamped scores was left untouched. Proven with a
test showing the exact same 8% synthetic move no longer clamps the
recalibrated factors while still correctly clamping an untouched one
(CPI) — confirming the fix is targeted, not a blanket loosening.

Full account in
[`docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md`](docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md).

**568 passing tests total.**

## Update: all 16 Macro factors now backtestable — closing a previously-deferred gap

`docs/ARCHITECTURE_BACKTESTING.md` originally deferred Chief Macro
Officer's 10 survey-revised factors (CPI, GDP, NFP, etc.) as "genuinely
harder... a real, bounded follow-up." Built now, specifically so the
normalization thresholds just recalibrated above can eventually be
validated against real historical data, not just reasoned defensibly.

`connectors/fred_historical.py` gained `fetch_point_in_time_history()` —
a full vintage-correct 5-observation window (not just a single value),
matching exactly what the live agent fetches. `agents/backtest_signals.py`'s
new `macro_factor_signal()` reads each factor's exact normalization
threshold directly from `agents.chief_macro_officer._FACTOR_SPECS` —
never a duplicated copy that could drift out of sync — proven with a test
showing the same synthetic move clamps for CPI (still 5.0) but not for
Initial Jobless Claims (now 15.0), reading the live calibration, not a
hardcoded test value. All 16 factors are now valid `--signal` choices in
`scripts/run_backtest.py`, e.g.
`--signal "Initial Jobless Claims" --asset SPY`.

Full account in
[`docs/ARCHITECTURE_BACKTESTING.md`](docs/ARCHITECTURE_BACKTESTING.md).

**580 passing tests total.**

## Update: a real bug found via your live backtest run

Running `python scripts/run_backtest.py --signal "Initial Jobless Claims"
--asset SPY` with a real FRED key confirmed the FRED side worked
perfectly (61 of 61 dates), but silently returned "0 daily closes" for
the price side — no error, no crash, just an empty, misleading result.

Root cause: `connectors/yahoo_history_connector.py` builds its date
field as `"2026-08-05T00:00:00"` (a pandas Timestamp's `.isoformat()`,
with a time component), but `run_backtest.py` parsed dates with a
date-only `strptime` format, which raised on every single row — silently
swallowed by an exception handler written to skip a handful of genuinely
malformed rows, not every row uniformly. Fixed with
`datetime.fromisoformat()`, verified against every realistic variant
(bare, timezone-aware, with microseconds). This is a clean example of why
live verification matters even after extensive synthetic testing — no
hand-written test happened to reproduce the exact string shape the real
connector actually produces.

Full account in
[`docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md`](docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md).

**586 passing tests total.**

## Update: a second real finding from the same session — overlapping test windows

After the date-parsing fix, re-running the backtest with a tighter
`--step-days 7` (to better match Initial Jobless Claims' weekly reporting
cadence) surfaced a genuine statistical gap: with the default 20-day
forward window, consecutive test dates' return windows overlapped by 13
days — meaning those "samples" weren't independent, but the significance
threshold (which assumes independence) didn't flag this at all.

Fixed at the engine level, not just the one script: `agents.backtest_engine.run_backtest()`
now detects when consecutive test dates are spaced closer than the
forward-return window and appends a clear, honest caveat to the result's
interpretation — explaining exactly what it means and how to get a
cleaner test. Since the CLI script already prints that interpretation,
every future run gets this warning automatically, and so does every other
current or future caller of the engine.

Full account (both this and the date-parsing fix) in
[`docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md`](docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md).

**590 passing tests total.**

## Update: a third real finding — no rate-limit pacing

Comparing the user's two identical backtest runs directly surfaced it:
the same exact command returned 240 of 261 usable signal readings the
first time, only 220 the second — consistent with FRED's rate limit
being hit partway through, since the script fired ~261 requests in a
tight loop with zero delay between them, a risk flagged earlier but not
yet fixed. Now paced with a configurable `--request-delay` (default 0.6s)
— correctly skipped entirely for Seasonality, which makes no network
requests at all, proven directly with tests showing zero `time.sleep()`
calls for that signal and the exact expected count/delay for a FRED-based
one.

Full account (all three fixes from this session) in
[`docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md`](docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md).

**594 passing tests total.**

## Update: the same over-clamping pattern found again, this time with your EIA key

Once `EIA_API_KEY` was confirmed working, Crude Oil Inventories clamped
at the exact `+100.0` extreme — the identical signature that led to the
Macro factor recalibration. Same cause: crude oil and especially natural
gas inventories swing significantly over their fetch window due to
well-documented seasonal patterns (summer draws, winter withdrawals), so
the original uniform 5% threshold was too tight. Widened Crude Oil
Inventories to 10.0 and Natural Gas Storage to 20.0 (natural gas has a
substantially more pronounced seasonal cycle); Gold's three factors were
left untouched since that same run showed them producing sensible,
non-clamped scores already. Proven with a test showing the same synthetic
seasonal-scale move no longer clamps either commodity, and Natural Gas
scores measurably closer to neutral than Crude Oil for the identical
input.

Full account (all fixes) in
[`docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md`](docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md).

**595 passing tests total.**

## Update: proactive audit found the same pattern in a third department

Rather than wait for a third live run to catch the next instance,
searched the whole codebase for other uses of the same uncalibrated
trend-scoring default that caused both prior recalibrations. Found three
more call sites — handled with honestly different confidence levels:

- **Chief Cryptocurrency Analyst's Open Interest** — widened to 20.0.
  Crypto open interest volatility is well-established, not disputed, so
  this is a reasoned proactive fix (unlike the other two, not yet backed
  by an actual live clamped run).
- **Chief Bond Strategist's Treasury yield trend** and **Chief Equity
  Analyst's EPS/Revenue trend** — deliberately left unchanged. Neither
  has a strong enough a priori case for a specific new number (Treasury
  yields are lower-volatility daily data; company growth rates vary too
  much by company for one uniform correction to be defensible). Flagged
  as worth testing live rather than guessed at.

Full account (all fixes) in
[`docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md`](docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md).

**596 passing tests total.**

## Update: a real data integrity bug — 8-year-stale Revenue data

Verifying Chief Equity Analyst live for the first time (after fixing an
unrelated `.env` mistake — a duplicate `SEC_USER_AGENT` line, one empty,
shadowing the real one) surfaced something serious: EPS came back dated
correctly (2026), but Revenue came back dated **2018-09-29** — eight
years stale, yet reported with full `quality_score: 100.0` confidence.

Root cause: Apple (like most US public companies) switched which XBRL
tag it files total revenue under around 2018, when the ASC 606
accounting standard took effect. The old tag, `Revenues`, didn't start
erroring — it just stopped receiving new filings, so querying it still
returns a perfectly valid response: the last thing ever filed under it.
No error, no empty response — nothing that existing error handling could
catch.

Fixed by having the connector try both the primary tag and known
fallback tags, keeping whichever has the MOST RECENT filing date — not
simply whichever succeeds first, since the stale tag succeeds too. Wired
into every real call site that fetches Revenue. EPS was left untouched;
it has no known equivalent issue, and guessing at a fix without evidence
would be worse than no fix at all.

Full account (including the `.env` duplicate-key issue) in
[`docs/ARCHITECTURE_SEC_STALE_REVENUE_FIX.md`](docs/ARCHITECTURE_SEC_STALE_REVENUE_FIX.md).

**601 passing tests total.**

## Update: a second, more significant bug found in the same investigation

After the stale-tag fix, Revenue's date came back correct — but the
overall bias was STILL pinned at exactly `+100.0`, even with genuinely
fresh data. Root cause: the connector filtered filings by FORM TYPE alone
(10-Q vs 10-K), but never checked the actual reporting PERIOD LENGTH — a
10-K commonly includes quarterly comparative figures, a 10-Q sometimes
reports 6/9-month year-to-date cumulative figures. That meant the "trend"
could genuinely be comparing one quarter's EPS against a full year's EPS
as if they were sequential data points — a huge, meaningless swing that
would clamp the score at its maximum almost regardless of any threshold,
since the underlying comparison was invalid from the start.

Fixed by computing each filing's actual duration and bucketing into
quarterly (~90 days) or annual (~365 days) — never mixed, preferring
quarterly when there's enough for a real trend, falling back to annual
otherwise, raising clearly (handled the same as any other data-fetch
failure) when no consistent-period series exists at all.

Full account in
[`docs/ARCHITECTURE_SEC_STALE_REVENUE_FIX.md`](docs/ARCHITECTURE_SEC_STALE_REVENUE_FIX.md).

**604 passing tests total.**

## Update: a third bug — found via a diagnostic tool built specifically to investigate it

Still getting wildly different results across consecutive runs (+100.0
with EPS $6.88, then -100.0 with EPS $2.02, same company, same date), a
new tool (`scripts/debug_sec_edgar_raw.py`) was built to dump SEC's raw
data directly rather than guess at a third fix. The user ran it against
real Apple data, and it showed the real cause: **many entries appear as
exact duplicates** (2-4 times each). Left undeduplicated, these silently
consumed slots in the comparison window — reconstructing the user's real
data confirmed it precisely: 4 duplicate entries pushed a genuinely older
quarter out, landing the comparison on Apple's holiday quarter (naturally
the highest of the year) against a summer quarter (naturally lower) — a
seasonal artifact, not a real business change, that clamped to exactly
-100.0.

Fixed by deduplicating entries before any bucketing. The same real data,
after the fix, correctly reaches 7 distinct quarters and produces a
sensible +32.0% trend, matching Apple's real growth.

**One honest, still-open limitation**: deduplication fixes the specific
bug found, but doesn't fully guarantee same-quarter, year-over-year
comparisons in every case — a deeper design question (treating equity
seasonality as a first-class concept, the way commodity seasonality
already is elsewhere in this platform) flagged for the future rather
than solved here.

Full account in
[`docs/ARCHITECTURE_SEC_STALE_REVENUE_FIX.md`](docs/ARCHITECTURE_SEC_STALE_REVENUE_FIX.md).

**606 passing tests total.**

## Update: Chief Commodity Analyst / Chief FX Analyst investigated — verdict: correct, just confusingly worded

A live EUR/USD run showed a "25th percentile, normal range" reading
sitting next to a maxed-out -100.0 bias score — looked like a
contradiction. Investigated properly rather than assumed: pulled the
real 8-week net-position numbers directly and traced them through the
scoring formula by hand. The real data showed a genuine, severe
reversal (net +34,353 to net -58,091 over 8 weeks) — the -100.0 score
is honest and correct. The percentile is also correct — today's reading
just isn't the single most extreme value within that same window, since
the week before was slightly more negative.

Both numbers were right; nothing explained why they weren't in tension.
Fixed with a wording-only change — the percentile evidence now explicitly
states it measures a different question (where today sits within its own
recent range) than the trend score (the size of the overall multi-week
swing), and that the two can genuinely disagree without contradicting
each other. No scoring logic changed.

Full account in
[`docs/ARCHITECTURE_COT_PERCENTILE_CLARITY.md`](docs/ARCHITECTURE_COT_PERCENTILE_CLARITY.md).

**607 passing tests total.**

## Update: Chief Sentiment Officer's news feed was returning the wrong content entirely

A live run scored exactly `0.0` — not automatically suspicious for a
small keyword scorer on its own, so the actual 10 fetched headlines were
inspected directly rather than assumed innocent. All 10 were MarketWatch
personal-finance advice columns ("should I pay off my mortgage?", "how
do I care for my elderly relative?") — zero had anything to do with
markets, despite the feed being labeled "top stories."

Built `scripts/debug_news_feeds.py` to test several candidate feeds side
by side rather than guess at a replacement. The user ran it live, twice
confirming the original feed's problem and finding a genuinely working
alternative — MarketWatch's MarketPulse feed, which returned real
economic data releases, real corporate news, and an actual sentiment
keyword match. Two other candidates failed for unrelated reasons and
were correctly left unused, since neither was confirmed working.

`NEWS_RSS_URL`'s default is now the confirmed-working feed. Anyone with
their own `NEWS_RSS_URL` already set in `.env` is unaffected.

Full account in
[`docs/ARCHITECTURE_NEWS_FEED_FIX.md`](docs/ARCHITECTURE_NEWS_FEED_FIX.md).

**607 passing tests total (unchanged — no test hardcoded the old URL).**

## Update: re-running a department was silently double-weighting it

Testing the Trade Decision Engine live surfaced a session pool with 7
entries for 5 actual department runs — Chief Macro Officer and Chief
Risk Fundamentals Officer had both been run twice, and both copies were
sitting in the pool together. Root cause: the dashboard only ever
appended to the report list, never replacing an existing entry for the
same department+asset — and `ChiefStrategyOfficer.synthesize()` had zero
defense against a duplicated department, meaning it silently counted
TWICE in the weighted bias average. A genuine correctness bug, not
cosmetic — any Strategy Synthesis or Trade Decision Engine run after
re-running any department even once could have been affected.

Fixed at both ends: the dashboard now replaces rather than duplicates
when re-running a department, and `synthesize()` itself now defensively
deduplicates by department name regardless of what any caller passes in.

A related concern from the same live run — empty-looking Evidence/Risks
sections — was investigated directly rather than assumed broken, and
turned out to be a Streamlit expander-collapsed-by-default copy-paste
artifact, not a real bug. Verified with real, correct text underneath.

Full account in
[`docs/ARCHITECTURE_DUPLICATE_DEPARTMENT_FIX.md`](docs/ARCHITECTURE_DUPLICATE_DEPARTMENT_FIX.md).

**611 passing tests total.**

## Update: Trade Decision Engine's four momentum explanations were all identical

Live testing showed Fundamental, Technical, Risk, and Overall momentum
all displaying the exact same "why" explanation — including COT
positioning language shown as the reason the TECHNICAL score moved, even
though Technical Score is computed purely from RSI/MACD/SMA price data
and has nothing to do with COT positioning. Root cause: all four calls
to the momentum explainer were passed the same merged, whole-decision
catalysts/risks list, rather than each score's own contributing data.

Fixed by building genuinely component-specific catalysts/risks before
each call — Fundamental and Risk now filter to just their own
contributing departments, Technical pulls directly from the synthetic
technical report's own real evidence. Overall correctly keeps using the
full merged list, since explaining the overall score legitimately draws
from everything.

A related concern from the same test — an empty-looking "why unchecked
items failed" section — was investigated and confirmed to be the same
collapsed-expander copy-paste artifact found earlier, not a bug.

Full account in
[`docs/ARCHITECTURE_MOMENTUM_EXPLANATION_FIX.md`](docs/ARCHITECTURE_MOMENTUM_EXPLANATION_FIX.md).

**612 passing tests total.**

## Update: Telegram send failures were hiding their actual cause

Live testing of a real Telegram send hit a genuine `400 Bad Request` —
but the error message gave no way to tell whether the chat ID was wrong
or the message text itself had a formatting problem, two completely
different issues. Root cause: the code called `raise_for_status()`
immediately, which raises before ever reading the response body —
throwing away Telegram's own `description` field, which explains exactly
what went wrong even on error status codes.

Fixed by reading the response body first, so Telegram's real explanation
surfaces regardless of which kind of failure occurred. Doesn't fix the
original send failure by itself — makes the actual reason visible so it
can finally be diagnosed on the next attempt.

Full account in
[`docs/ARCHITECTURE_TELEGRAM_ERROR_REPORTING_FIX.md`](docs/ARCHITECTURE_TELEGRAM_ERROR_REPORTING_FIX.md).

**615 passing tests total.**

## Update: batch backtesting — every signal against one asset, in one run

Testing individual signals one at a time across several sessions made
clear that comparing many candidate factors really needs one shared run,
not 21 separate ones. `scripts/run_backtest_all.py` runs every available
signal (or a chosen subset via `--signals`) against one asset in a
single command, fetching price history exactly once — proven directly
with a test — and sorting the final comparison table by strongest
correlation first, the way a real quant researcher would actually want
to screen many factors at once.

```
python scripts/run_backtest_all.py --asset SPY
python scripts/run_backtest_all.py --asset SPY --signals "vix,GDP,Initial Jobless Claims"
```

Built entirely on top of the already-tested single-signal infrastructure
— no duplicated scoring or significance logic. Honest scope note: testing
every Macro factor at once means real, individually-paced FRED requests
per date per factor, so a full run is measured in tens of minutes, not
seconds — inherent to FRED's API, not this script.

Full account in
[`docs/ARCHITECTURE_BATCH_BACKTESTING.md`](docs/ARCHITECTURE_BATCH_BACKTESTING.md).

**620 passing tests total.**

## Update: strategy-level backtesting — simulated trades, not just correlation

The first step toward closing the gap between "research tool" and "quant
machine": `agents/strategy_backtest.py` simulates actual trades from a
signal — entries, exits, transaction costs, a real equity curve — and
reports genuine strategy metrics (Sharpe, Sortino, win rate, profit
factor, strategy-level max drawdown), distinct from the existing
correlation-only validation.

```
python scripts/run_strategy_backtest.py --signal seasonality --asset Gold
```

Still purely research — no broker connection, no real position, the same
design this platform has held to since Phase 1. A real unit-mismatch bug
was caught and fixed before shipping: the first draft would have scaled
every Sharpe ratio wrong by two orders of magnitude by reusing a
volatility function with an incompatible unit convention, caught by
checking its actual signature before wiring it in.

Full account in
[`docs/ARCHITECTURE_STRATEGY_BACKTESTING.md`](docs/ARCHITECTURE_STRATEGY_BACKTESTING.md).

**637 passing tests total.**

## Update: portfolio construction — position sizing and multi-asset allocation

The second real piece toward closing the "quant machine" gap:
`agents/portfolio_construction.py` adds fixed-fractional and Kelly
position sizing (the Kelly variant connects directly to real simulated
trade history from strategy backtesting), plus inverse-volatility
weighting and position/gross-exposure constraints for allocating across
multiple assets at once.

```
python scripts/build_portfolio.py --assets "Gold:GC=F,SPY:SPY,TLT:TLT"
```

Still purely research/planning — proposes an allocation, doesn't execute
anything. Honest about what it doesn't do: correlation between assets
isn't modeled (documented plainly, a natural harder follow-up on top of
Chief Risk Officer's already-real correlation math). Kelly verified
against the classic textbook example; vol-target weighting verified for
the exact expected inverse relationship; constraint capping's "don't
force-redistribute freed capacity" behavior deliberately tested and
documented as a real design choice, not a bug.

Full account in
[`docs/ARCHITECTURE_PORTFOLIO_CONSTRUCTION.md`](docs/ARCHITECTURE_PORTFOLIO_CONSTRUCTION.md).

**657 passing tests total.**

## Update: the execution layer — the first component that can touch real capital

The third piece toward the "quant machine" roadmap, and the one where
the stakes genuinely change. `brokers/alpaca_connector.py` and
`agents/execution_engine.py` add real broker connectivity and order
planning — but with a safety model built to be very hard to circumvent
by accident:

- **Paper trading only, by default, always.** Live trading requires
  `live_trading_confirmed=True` written explicitly in Python code, every
  time — not a `.env` setting, not an environment variable, checked with
  `is not True` so no truthy-but-wrong value (`1`, `"true"`, `"yes"`) can
  ever enable it. Proven directly across 8 different sneaky values in a
  parametrized test.
- **Dry-run by default**, as a separate protection layer on top of
  paper-vs-live — proven against a broker that raises an exception if
  any method is called at all.
- **No live-trading flag anywhere in any script this platform ships.**

**Honest limitation, stated plainly**: unlike every other connector in
this project, this one has not been verified against a real API
response — no network access here, no real account to test against.
Treat it with real skepticism and test thoroughly against paper before
trusting it for anything.

```
python scripts/demo_execution_engine.py
python scripts/demo_execution_engine.py --connect-paper
```

Full account in
[`docs/ARCHITECTURE_EXECUTION_LAYER.md`](docs/ARCHITECTURE_EXECUTION_LAYER.md).

**698 passing tests total.**

## Update: live risk monitoring — the fourth quant-machine piece

`agents/circuit_breaker.py` and `agents/risk_monitor.py` add real-time
drawdown tracking against configurable thresholds, tied to the
already-real Chief Risk Officer for actual portfolio VaR/volatility/
correlation. Read-only by design — nothing here can place, modify, or
cancel an order, proven directly with a broker whose order methods raise
if called at all — a meaningfully lower-risk surface than the execution
layer, so it doesn't need the same multi-layer opt-in structure.

The circuit breaker checks daily loss and total drawdown-from-peak
independently, both reported if both are breached, with the exact
boundary case (a loss of precisely the configured limit) proven to
trigger correctly.

```
python scripts/monitor_risk.py
python scripts/monitor_risk.py --loop --interval-seconds 300
```

`--loop` tracks daily-starting and all-time-peak equity across
iterations and alerts via the same, already-proven `TelegramAlerter` on
a trip — no new alerting code. Same honest limitation as the rest of the
execution layer: not exercised against a real broker from this
environment; the threshold math is independently verified, the
real-broker wiring is not.

Full account in
[`docs/ARCHITECTURE_RISK_MONITORING.md`](docs/ARCHITECTURE_RISK_MONITORING.md).

**715 passing tests total.**

## Update: the execution layer verified live — and a full end-to-end pipeline

The Alpaca connector was tested against a real paper account for the
first time. Every core method passed on the first attempt: real account
equity matched the dashboard exactly, `is_paper` correctly held `True`
under real conditions, a real 1-share AAPL order was submitted and
filled, and `get_order_status()`/`get_positions()` independently agreed
on the exact same real fill. This is the first genuinely live-verified
result anywhere in the execution layer.

`scripts/run_full_pipeline.py` ties the whole roadmap together in one
command: real price history → real volatility → real portfolio
weights → real broker state → a real rebalance plan, reusing every
already-tested piece with no duplicated logic. Same safety model as
everywhere else — dry-run by default, `--submit` required to place
anything, no live-trading flag anywhere.

```
python scripts/run_full_pipeline.py --assets "AAPL:AAPL,SPY:SPY"
```

Full account in
[`docs/ARCHITECTURE_EXECUTION_LAYER.md`](docs/ARCHITECTURE_EXECUTION_LAYER.md)
and
[`docs/ARCHITECTURE_FULL_PIPELINE.md`](docs/ARCHITECTURE_FULL_PIPELINE.md).

**715 passing tests total (unchanged — this script is an orchestration layer over already-tested pieces).**

## Update: cloud deployment infrastructure

`Dockerfile`, `docker-compose.yml`, and `.dockerignore` package the
platform for deployment to a real cloud server — the dashboard and,
optionally, the continuous risk monitor, as managed services. Secrets
are injected at container *runtime* via `env_file`, never baked into
the image (`.dockerignore` excludes `.env` explicitly) —
`config/settings.py`'s `load_dotenv()` never overrides variables
already present in the environment, so this works with zero code
changes.

**Honest limitation**: no Docker available in this environment, so this
hasn't been build-tested the way everything else eventually was —
treat it with the same caution the Alpaca connector had before its
first real run.

**A real security note, not just a suggestion**: the dashboard ships
with no authentication. Once real credentials are set, it shows real
account data. `docs/ARCHITECTURE_CLOUD_DEPLOYMENT.md` covers firewall
restrictions and a reverse-proxy option before ever exposing it to the
open internet.

**715 passing tests total (unchanged — infrastructure files, not application code).**

## Update: cross-asset-class opportunity screener

`agents/opportunity_screener.py` scans many assets across equities,
commodities, FX, and crypto and ranks them by a real technical
**conviction score** — deliberately, honestly NOT a backtested
win-probability (that requires `agents/strategy_backtest.py`'s much
slower per-asset simulation). A high score here means a real signal is
currently strong and worth deeper backtesting, not a validated winner.

```
python scripts/run_screener.py
python scripts/run_screener.py --max-equities 100 --min-confidence 50 --build-portfolio
```

Reuses the platform's existing curated asset universe and the
already-tested portfolio construction and execution pipeline — no
duplicated logic. `--build-portfolio` turns the ranked list into a real
allocation and rebalance plan; same safety model as everywhere else,
dry-run by default, no live-trading flag anywhere.

**A separate real fix made while restoring this environment**: a newer
Streamlit release changed how test paths resolve, breaking 25 dashboard
tests — not a platform bug, fixed by resolving every test path to an
absolute one rather than leaving it environment-dependent.

**732 passing tests total.**

## Update: a real cross-asset-class ranking bias, found via live testing, fixed

A real screener run across equities, commodities, FX, and crypto came
back 100% volatile growth stocks in the top 10 — zero commodities, FX,
or crypto, despite scanning all of them. Root cause: ranking used a
flat 5% normalization threshold applied uniformly to every asset — a
routine move for a volatile growth stock, but a rare, significant one
for a major FX pair, so volatile assets structurally dominated the
ranking regardless of which asset class genuinely had the best
opportunity.

Fixed with a new, additive function —
`agents.technical_indicators.volatility_normalized_trend_score()` —
that normalizes by each asset's own volatility instead of a flat
percentage. The existing `trend_score()` is completely unchanged,
still used exactly as before everywhere else in the platform. Proven
directly at the full CLI level: five assets given the identical
underlying trend, differing only in volatility, now correctly rank the
calm ones (EUR/USD, Gold) above the volatile growth stocks — the exact
opposite of what the original, biased version produced for the same
inputs.

**740 passing tests total.**

## Update: verified again live — the fix held, but a real open question remains

Re-running the exact same scan after the fix still returned a top 10
that was 100% equities. The controlled fix is proven correct (twice,
including at full CLI level) — the honest question is whether the
real-world result reflects genuine market structure (individual stocks
are well-documented in academic finance to show more persistent,
company-driven trends than broad FX/commodity indices, even relative to
their own volatility) or something not yet fully accounted for. Not
resolved either way — `ScreenedOpportunity` now exposes each asset's own
`annualized_vol_pct` directly in the output table, so this can be
checked against real numbers rather than trusted blindly.

**A second real environment fix, found on the same run**: a dashboard
test timed out at 30s on a real network-connected machine — not a
platform bug, just too short a timeout for a real network refreshing
many sources at once (a sandboxed, network-less test environment never
has to wait that long). Fixed by raising that one test's timeout to 90s.

**741 passing tests total.**

## Update: fairness confirmed, diversification added as a deliberate choice

Checking real volatility figures behind a live result confirmed the
scoring fix genuinely works — nothing suspicious, all realistic numbers.
What the same run revealed instead: a fair ranking and a diversified one
are different goals. A fair ranking can still legitimately return mostly
one asset class if that class simply has stronger signals right now —
an honest reflection of current conditions, not a bug.

`--diversify --top-n-per-class 3` guarantees representation from every
scanned asset class, as an explicit, separate, opt-in choice on top of
the (already correct) fair scoring — reusing the existing ranking logic
per class rather than duplicating it. Verified directly at the full CLI
level with realistic mixed-asset data: commodity, FX, and equity
candidates all appear together even when equities' raw scores are a
fraction of the others'.

**746 passing tests total.**

## Update: a critical fix — non-tradeable asset classes were reaching order construction

Testing `--diversify --build-portfolio` produced real orders like
`NZD/USD BUY 29138.33` — mathematically correct given the dollar
allocation, but for an asset class Alpaca's Trading API cannot trade
under any circumstances (confirmed via research: equities and crypto
only, no forex, no commodities). Had `--submit` been used on that exact
result, every one of those orders would have been rejected or worse.
The most severe finding in this project to date — a correctness issue,
not a ranking-quality one.

Fixed by explicitly filtering to `{"equity", "crypto"}` before
`--build-portfolio` constructs anything. Commodity/FX candidates still
appear in the screening output — real, useful signal regardless of
whether this broker can act on it — but are now clearly, honestly
excluded from the executable plan, naming exactly what was excluded and
why. Proven directly with the user's exact real scenario reconstructed,
plus the zero-tradeable-candidates edge case.

**750 passing tests total.**

## Update: excluded candidates get a genuine, full-detail section

Commodity/FX candidates excluded from the executable portfolio (Alpaca
can't trade them) now get their own `=== Manual Trading Candidates ===`
table — same bias/confidence/volatility/conviction detail as the main
ranking, for anyone who wants to act on them manually via a different
platform, rather than just a bare list of names.

**751 passing tests total.**

## Update: retry logic for intermittent Yahoo failures

Repeated real runs showed large, genuinely-listed companies (Meta,
Starbucks, Synopsys) failing as "possibly delisted" — misleading;
they're not delisted, Yahoo's unofficial endpoint just intermittently
returns nothing. The failures are genuinely random, not tied to scan
position or request rate (slowing every request down didn't reliably
help on a follow-up run).

`_fetch_price_history()` — the one shared function used by every
backtesting and screening script — now retries up to twice, 2 seconds
apart, before giving up, so every caller benefits automatically. A
ticker that still fails still raises the real error; the common
no-failure case never sleeps at all. Full account in
[`docs/ARCHITECTURE_FETCH_RETRY.md`](docs/ARCHITECTURE_FETCH_RETRY.md).

**755 passing tests total.**

## Update: volume confirmation scoring

Every technical score on the platform was pure price action — no volume
used anywhere, a real, acknowledged gap (a move on heavy volume means
something different from the same move on thin volume, classical
technical analysis going back to Dow Theory). Fixed additively: Yahoo
volume is now fetched, and `agents/opportunity_screener.py`'s conviction
score gets a bounded [0.85, 1.15] adjustment — elevated recent volume
boosts it, below-average volume reduces it. Missing/unusable volume data
(common for FX pairs) maps to an exactly neutral 1.0, never a penalty —
deliberately, to avoid repeating the cross-asset-class fairness mistake
found and fixed earlier for `trend_score()`.

**Considered and deliberately set aside**: BOS/CHOCH (Smart Money
Concepts). Popular in retail trading circles, but considerably more
subjective and less rigorously grounded than volume confirmation — if
built, it should be an explicit, backtested experiment, not trusted on
reputation. Full account in
[`docs/ARCHITECTURE_VOLUME_CONFIRMATION.md`](docs/ARCHITECTURE_VOLUME_CONFIRMATION.md).

**776 passing tests total.**

## Update: a real duplication in the Trade Decision Engine, found via live dashboard review

The Entry Confirmation Checklist showed Market Structure, Breakout, and
Volume as three independent confirmations. They weren't — all three were
driven by the exact same MACD/SMA proxy, a documented placeholder from
an earlier phase. Fixed in two parts: Volume now uses the platform's
real volume confirmation logic (the data was already flowing through
`decide()`, just unused for this) — fully backward compatible when
omitted. Breakout was removed entirely rather than "fixed," since making
it genuinely independent would mean building real BOS/CHoCH structural
detection — the same methodology already set aside earlier the same day
for being too subjective. `all_passed()`'s actual gating behavior is
unchanged; only the honesty of what's displayed improved.

**780 passing tests total.**

## Update: COT release schedule awareness + weekly sentiment digest

**COT release schedule**: `config/refresh_intervals.py` had long
acknowledged a gap in its own comment — the flat 7-day COT refresh timer
drifts out of alignment with the CFTC's real, fixed weekly schedule
(every Friday, 3:30pm ET) over time. `agents/release_schedule.py` checks
the actual schedule directly, correctly handling EST/EDT automatically.
The Data Health page now shows the real most-recent and next-expected
release times, and flags genuine staleness against the real schedule.
Honest limitation: doesn't account for holiday-shifted releases.

**Weekly sentiment digest**: aggregates a week of saved Chief Sentiment
Officer reports (bias trend, average confidence, top recurring
catalysts/risks) rather than only showing the latest snapshot. Important
honest dependency: this needs real accumulated history to summarize —
an interactive dashboard click alone doesn't populate it; the existing
scheduled workflow (`.github/workflows/scheduled_run.yml` /
`scripts/run_daily_cycle.py`) does. Full account in
[`docs/ARCHITECTURE_COT_RELEASE_SCHEDULE.md`](docs/ARCHITECTURE_COT_RELEASE_SCHEDULE.md)
and
[`docs/ARCHITECTURE_WEEKLY_DIGEST.md`](docs/ARCHITECTURE_WEEKLY_DIGEST.md).

**801 passing tests total.**

## Update: Swing Signal — the same COT data, read for a swing trader instead of a position trader

Every existing department is built for a position trader: a COT reversal
against the standing multi-week trend is treated as a *risk* to a thesis
already held (`MOMENTUM_REVERSAL_PENALTY = -15.0` in
`agents/positioning_agent_base.py`). A swing trader wants the opposite
read of the exact same data — the moment large speculator positioning
starts turning against its established trend is the entry setup itself,
not a reason to discount an existing position.

`agents/swing_signal.py` is a new, fully separate, additive pipeline
built on that reframing. It reuses the platform's existing COT reversal
classification (`classify_momentum_signal()`) and broad market news
scoring unmodified — nothing about the position-trading pipeline's own
behavior, confidence math, or tests changed to add this. A signal only
fires on a genuine `"reversal_watch"`; an extreme percentile reading is
now a confidence *bonus* rather than a penalty, since a reversal off a
crowded reading is a textbook mean-reversion setup. Delivered two ways:
a new **Swing Signals** dashboard page (live scan across the whole
configured FX/commodity watchlist, persisted history, manual Telegram
send) and automatically inside the existing scheduled daily cycle
(`scripts/run_daily_cycle.py`), which sends a Telegram alert via the
existing bot when credentials are configured — deduplicated to once per
real CFTC COT release (reusing `agents/release_schedule.py`), not once
per weekday cycle run. Honest limitation: the news cross-check is broad
market sentiment, not per-asset — this platform has no per-commodity or
per-currency news source. Full account in
[`docs/ARCHITECTURE_SWING_SIGNAL.md`](docs/ARCHITECTURE_SWING_SIGNAL.md).

**832 passing tests total.**
