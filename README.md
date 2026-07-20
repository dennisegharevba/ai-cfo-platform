# AI Chief Fundamental Officer Platform

An institutional-grade, multi-agent AI research platform that replicates the
workflow of an institutional trading research department — across
commodities, equities, indices, ETFs, futures, forex, bonds, and crypto.

**This is not a trading bot.** It never places trades. It produces
research, probability-based directional bias, and gated alerts (Telegram +
dashboard) for a human to act on.

Built in fully working, tested, documented phases. All 11 phases on the
original roadmap are now complete — all 12 Chief Officers, a dashboard,
and scheduled automation. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the
full history.

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

## Phase 5 (current): Chief Sentiment Officer + Chief Technical Officer

- Chief Technical Officer: RSI (20%) + MACD histogram (40%) + SMA(20/50)
  trend (40%) per ticker, via a new free Yahoo Finance history connector;
  flags overbought/oversold RSI as elevated risk
- Chief Sentiment Officer: free news-RSS headline sentiment (keyword-based,
  fully explainable — no ML black box), optionally blended with the same
  CFTC COT dataset a Chief Commodity/FX Analyst already reads, reinterpreted
  as a crowd-sentiment signal
- New pure-Python `agents/technical_indicators.py` (RSI/MACD/SMA — no
  numpy/pandas indicator libraries, every formula inspectable)

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

## Phase 9 (current): Chief Execution Officer — all 12 Chief Officers now built

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

- New `config/watchlist.py` — what the automated cycle covers, editable
  without touching code
- New `scripts/run_daily_cycle.py` — runs every watchlist entry through
  its configured departments, synthesizes, persists, and evaluates for
  alerting; one asset's failure is isolated and logged, never stops the
  rest of the cycle
- New `.github/workflows/scheduled_run.yml` — cron (weekdays 13:00 UTC) +
  manual trigger, credentials from GitHub Actions secrets, with the
  database persisted across ephemeral runners via `actions/cache` (the
  tradeoffs of that approach are documented honestly, not glossed over)

See [`docs/ARCHITECTURE_PHASE11.md`](docs/ARCHITECTURE_PHASE11.md) for the full design.

**225 passing tests total, CI on every push.**

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add your free FRED API key + SEC_USER_AGENT (+ Telegram credentials, optional)

# Run the dashboard:
streamlit run dashboard/Home.py

# Run the full automated research cycle manually:
python scripts/run_daily_cycle.py

# Or run any individual phase's demo script:
python scripts/demo_refresh.py
python scripts/demo_agents.py
python scripts/demo_commodity_fx_agents.py
python scripts/demo_equity_crypto_agents.py
python scripts/demo_sentiment_technical_agents.py
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
3. The workflow in `.github/workflows/scheduled_run.yml` runs automatically
   on its cron schedule, or trigger it manually from the **Actions** tab
   any time via "Run workflow"

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) and
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for details.

## Repository layout

```
core/          Data Integrity & Refresh Manager (Phase 1 — built)
connectors/    FRED, CFTC COT, Yahoo (quote + history), SEC EDGAR, Binance, News RSS
agents/        All 12 Chief Officers + BaseAgent/PortfolioAgent patterns (Phases 2-9 — complete)
models/        AgentReport, Portfolio, Position, StrategyReport, ExecutionDecision
database/      SQLite persistence: report_store.py, schema.py (Phase 8 — built)
telegram/      TelegramAlerter — free Bot API wrapper (Phase 9 — built)
dashboard/     Multi-page Streamlit app: Home.py + pages/ (Phase 10 — built)
config/        Settings, refresh intervals, watchlist.py (Phase 11 — built)
tests/         225 passing tests, network-independent (fake sources, mocked HTTP, AppTest)
scripts/       demo_*.py (Phases 1-9) + run_daily_cycle.py (Phase 11 — the production entry point)
docs/          Architecture (Phases 1-11), installation, configuration, roadmap
data/          Reserved: local caches/fixtures (not needed yet)
utils/         Shared logging setup
```

## This project is now complete

All 11 phases on the original roadmap are built, tested, and documented:
data integrity, all 12 Chief Officers, a dashboard, and scheduled
automation. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full history
and [`docs/ARCHITECTURE_PHASE11.md`](docs/ARCHITECTURE_PHASE11.md) for
natural next steps beyond the original spec.
