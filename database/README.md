# database/

Persistence layer for the Chief Learning Officer. Built in Phase 8:

- `schema.py` — SQLite table definitions (agent_reports, strategy_reports, outcomes)
- `report_store.py` — `ReportStore`, the low-level read/write layer

See docs/ARCHITECTURE_PHASE8.md and agents/chief_learning_officer.py (the
higher-level analytics wrapper other code should actually use).
