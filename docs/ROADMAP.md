# Roadmap

Each phase is built fully working, tested, and documented before the next
starts, per the project's delivery principle.

- [x] **Phase 1 — Data Integrity & Refresh Manager** (this delivery)
      `core/`, three real connectors (FRED, CFTC COT, Yahoo), 22 passing tests,
      CI workflow, full docs.
- [ ] **Phase 2 — Chief Macro Officer + Chief Bond Strategist**
      First two analytical agents, consuming data exclusively through
      `DataIntegrityManager`. Establishes the "agent" pattern the other ten
      officers will follow.
- [ ] **Phase 3 — Chief Commodity Analyst + Chief FX Analyst**
      Adds CFTC COT-driven positioning analysis, USDA/EIA/weather connectors.
- [ ] **Phase 4 — Chief Equity Analyst + Chief Cryptocurrency Analyst**
      Adds SEC EDGAR, earnings, and crypto exchange connectors.
- [ ] **Phase 5 — Chief Sentiment Officer + Chief Technical Officer**
      News/positioning sentiment, plus technical confirmation layer.
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
