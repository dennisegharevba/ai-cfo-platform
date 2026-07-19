# Architecture — Phase 10: Streamlit Dashboard

## First new dependency since Phase 1

Every prior phase deliberately avoided adding dependencies beyond what was
already justified (`requests`, `yfinance`, `python-dotenv`, `pytest`).
Streamlit is the first genuinely new one — justified because the spec
explicitly calls for a Streamlit dashboard, and there's no way to build one
without it.

## Structure: Streamlit's native multipage convention

```
dashboard/
    Home.py                          <- entry point: streamlit run dashboard/Home.py
    dashboard_utils.py                <- shared session-state + rendering helpers
    pages/
        1_Data_Health.py
        2_Department_Reports.py
        3_Strategy_Synthesis.py
        4_Risk_Officer.py
        5_Performance_Learning.py
        6_Alerts_Execution.py
```

This is Streamlit's own convention (a `pages/` directory next to the entry
script), not a custom router — Streamlit auto-generates the sidebar
navigation from the filenames.

## One shared `DataIntegrityManager` per session

`dashboard_utils.get_manager()` stores a single `DataIntegrityManager`
instance in `st.session_state`, created once and reused across every page
and every rerun within a session. This matters for the same reason it
mattered in every prior phase's demo scripts: a dataset registered and
fetched on the Data Health page is genuinely cached (within its TTL) when
the Department Reports page asks for the same key — Streamlit reruns the
whole script on every interaction, so without session-state sharing, each
page would otherwise get its own throwaway manager and re-fetch everything.

A new public method, `DataIntegrityManager.is_registered(key)`, was added
in this phase specifically so the dashboard pages (which register
connectors lazily, only when a page is first visited) don't need to reach
into the manager's private `_registrations` dict to check for a duplicate.

## The pipeline, end to end, across pages

```
1. Data Health           -> registers real connectors, shows live status_report()
2. Department Reports    -> runs any single BaseAgent/PositioningAgent live,
                            appends each AgentReport to session_state["last_agent_reports"]
3. Strategy Synthesis    -> ChiefStrategyOfficer.synthesize() over that session's
                            report pool for a chosen asset -> StrategyReport
4. Risk Officer          -> separate interactive portfolio builder (st.data_editor)
                            -> ChiefRiskOfficer.analyze_portfolio()
5. Performance & Learning -> records session reports into a REAL on-disk SQLite
                            file (not :memory:) via ChiefLearningOfficer, lets
                            the user log outcomes, shows analytics
6. Alerts & Execution    -> ChiefExecutionOfficer.evaluate() against the last
                            StrategyReport, with adjustable threshold sliders,
                            and an explicitly-confirmed real Telegram send
```

Pages 2 and 3 are the core loop: run departments live, then synthesize them
— exactly the same objects and methods the Phase 2-7 demo scripts use, not
a reimplementation for the UI. The dashboard is a presentation layer over
the existing agents, not a parallel system.

## Why the Learning Officer page uses a real file, not `:memory:`

Every other page's data (the report pool, the last synthesis) is
session-scoped and intentionally disposable — restart the dashboard, start
fresh. The Learning Officer is different: its entire purpose (Phase 8) is
a persistent history of reports and outcomes, so `get_learning_officer()`
backs it with `ai_cfo_platform.db`, a real file on disk, which survives
dashboard restarts. `.gitignore` was updated to exclude `*.db` — this is
runtime data, not something to commit.

## Safety rail on the Alerts & Execution page

Sending a real Telegram message from a dashboard button is exactly the
kind of action that shouldn't be one accidental click away. The send
button is disabled until an explicit confirmation checkbox is ticked, and
is disabled entirely if Telegram credentials aren't configured — mirroring
`scripts/demo_execution_officer.py`'s `--send-real` flag requirement from
Phase 9, just as a UI control instead of a CLI flag.

## Verifying the dashboard actually works — not just that it looks right

A dashboard is unusual among this platform's outputs: correctness isn't
fully verifiable by reading code, because Streamlit's runtime behavior
(session state, reruns, widget callbacks) has failure modes that only show
up when the app actually executes. Two levels of verification were used
here:

1. **A live headless smoke test** during development: `streamlit run` in
   the background, then `curl` every page route and the `/_stcore/health`
   endpoint, confirming the server boots and responds. This caught nothing
   by itself, though — a 200 response to a page route doesn't guarantee the
   page's Python actually ran, since modern Streamlit does client-side page
   routing.
2. **`streamlit.testing.v1.AppTest`** — Streamlit's own test harness, which
   genuinely executes a page's script (not just serves its HTML shell) and
   surfaces any exception. This is what `tests/test_dashboard_pages.py`
   uses, and it's real proof, not a mock: it caught a live
   deprecation warning (`use_container_width`, past its removal date) that
   the plain curl-based smoke test had missed entirely, which is exactly
   the class of bug this kind of test exists to catch.

## What's demonstrated in Phase 10

- `tests/test_dashboard_pages.py` — 12 tests using `AppTest`: every page
  renders without exception, AND the primary button on three pages (Data
  Health's refresh, Department Reports' run, Risk Officer's run) is
  actually clicked and confirmed not to crash — all with no network access
  (same as this repo's CI runners), proving every page degrades
  gracefully (blocked/low-confidence results) rather than crashing when
  data is unreachable, consistent with every prior phase's design
- 220 tests total across the whole project

## What's NOT in Phase 10 (coming later)

- Phase 11: GitHub Actions scheduled automation (running the pipeline on a
  schedule rather than via manual dashboard interaction)
- Dark mode / custom theming (Streamlit supports this via `.streamlit/config.toml`
  — not configured yet)
- True mobile-responsive layout tuning beyond Streamlit's own default
  responsive behavior
- Wiring `ExecutionDecision`s from the Alerts & Execution page into the
  Learning Officer's persistence automatically (currently separate manual
  steps on separate pages)
