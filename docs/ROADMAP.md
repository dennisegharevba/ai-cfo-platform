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
- [ ] **Phase 6 — Chief Risk Officer**
      Portfolio-level risk metrics (VaR, correlation, drawdown).
- [ ] **Phase 7 — Chief Strategy Officer**
      The synthesis layer: collects every department's report, resolves
      conflicts, produces the final institutional outlook.
- [ ] **Phase 8 — Chief Learning Officer + `database/`**
      Persistence for every report/alert/thesis/outcome; performance analytics.
- [ ] **Phase 9 — Chief Execution Officer + `telegram/`**
      Gated Telegram alerting once confidence/agreement thresholds are met.
- [ ] **Phase 10 — Streamlit dashboard (`dashboard/`)**
      Multi-page dashboard surfacing every department, starting with a
      data-health panel built directly on `DataIntegrityManager.status_report()`.
- [ ] **Phase 11 — GitHub Actions scheduled automation**
      Event-driven + scheduled refresh workflows once there are agents to feed.
