# Roadmap

Each phase is built fully working, tested, and documented before the next
starts, per the project's delivery principle.

- [x] **Phase 1 — Data Integrity & Refresh Manager** (this delivery)
      `core/`, three real connectors (FRED, CFTC COT, Yahoo), 22 passing tests,
      CI workflow, full docs.
- [x] **Phase 2 — Chief Macro Officer + Chief Bond Strategist** (this delivery)
      First two analytical agents (`agents/`), consuming data exclusively
      through `DataIntegrityManager` via the new `BaseAgent` template method
      pattern. Shared `AgentReport` output model (`models/report.py`). 17 new
      tests (39 total), `scripts/demo_agents.py`. See
      `docs/ARCHITECTURE_PHASE2.md`.
- [x] **Phase 3 — Chief Commodity Analyst + Chief FX Analyst** (this delivery)
      Per-market agents built on a new shared `PositioningAgent` base
      (`agents/positioning_agent_base.py`), driven by CFTC COT speculative
      positioning trend + crowded-positioning risk flagging. Extended
      `CotConnector` to fetch multi-week history instead of a single
      snapshot. 19 new tests (58 total),
      `scripts/demo_commodity_fx_agents.py`. See
      `docs/ARCHITECTURE_PHASE3.md`.
- [x] **Phase 4 — Chief Equity Analyst + Chief Cryptocurrency Analyst** (this delivery)
      New `SecEdgarConnector` (free XBRL fundamentals) and
      `BinanceFuturesConnector` (free futures OI + funding rate). Extracted
      shared `agents/trend_scoring.py` (third-consumer trigger). New
      `agents/crypto_scoring.py` for funding-rate-based sentiment/crowding.
      35 new tests (93 total), `scripts/demo_equity_crypto_agents.py`. See
      `docs/ARCHITECTURE_PHASE4.md`.
- [x] **Phase 5 — Chief Sentiment Officer + Chief Technical Officer** (this delivery)
      New `NewsRssConnector` (free RSS, stdlib XML parsing) and
      `YahooHistoryConnector` (free daily-close history). New
      `agents/technical_indicators.py` (pure-Python RSI/MACD/SMA) and
      `agents/sentiment_scoring.py` (keyword-based headline sentiment).
      Chief Sentiment Officer optionally blends in the same COT dataset a
      Chief Commodity/FX Analyst already reads, reusing Phase 3's
      positioning-scoring functions. 39 new tests (132 total),
      `scripts/demo_sentiment_technical_agents.py`. See
      `docs/ARCHITECTURE_PHASE5.md`.
- [x] **Phase 6 — Chief Risk Officer** (this delivery)
      A genuine architectural branch point: new `PortfolioAgent` base class
      (`agents/portfolio_agent_base.py`) for agents that analyze a whole
      Portfolio of positions rather than one asset/theme, plus new
      `Portfolio`/`Position` models. New pure-Python
      `agents/risk_calculations.py` (volatility, historical VaR, max
      drawdown, correlation). No new connector — reuses Phase 5's
      `YahooHistoryConnector` across multiple symbols. 25 new tests
      (157 total), `scripts/demo_risk_officer.py`. See
      `docs/ARCHITECTURE_PHASE6.md`.
- [x] **Phase 7 — Chief Strategy Officer** (this delivery)
      The synthesis layer, and a third architectural shape: fetches no
      data itself, only consumes AgentReports other agents already
      produced. Confidence-weighted synthesis across departments (weight ×
      confidence/100), a disagreement penalty via weighted standard
      deviation of bias scores, special handling for the always-neutral
      Chief Risk Officer report (excluded from bias math, still escalates
      risk_level), and templated trade-thesis/investment-committee-summary
      text. Extracted shared `agents/risk_severity.py`. New
      `models/strategy_report.py`. 14 new tests (171 total),
      `scripts/demo_strategy_officer.py`. See `docs/ARCHITECTURE_PHASE7.md`.
- [x] **Phase 8 — Chief Learning Officer + `database/`** (this delivery)
      A fourth architectural shape: no `analyze()` method at all — a
      persistence sink and performance-analytics query engine. New
      SQLite-based `database/report_store.py` + `database/schema.py`
      (stdlib only, no new dependency). `department_performance_summary()`
      and `strategy_accuracy_summary()` analytics methods. 19 new tests
      (190 total), `scripts/demo_learning_officer.py`. See
      `docs/ARCHITECTURE_PHASE8.md`.
- [ ] **Phase 9 — Chief Execution Officer + `telegram/`**
      Gated Telegram alerting once confidence/agreement thresholds are met.
- [ ] **Phase 10 — Streamlit dashboard (`dashboard/`)**
      Multi-page dashboard surfacing every department, starting with a
      data-health panel built directly on `DataIntegrityManager.status_report()`.
- [ ] **Phase 11 — GitHub Actions scheduled automation**
      Event-driven + scheduled refresh workflows once there are agents to feed.
