# dashboard/

Multi-page Streamlit app. Built in Phase 10.

Run with:
    streamlit run dashboard/Home.py

- `Home.py` — entry point / overview
- `dashboard_utils.py` — shared session-state + rendering helpers
- `pages/` — one file per page (Streamlit's native multipage convention;
  sidebar navigation is auto-generated from these filenames)

See docs/ARCHITECTURE_PHASE10.md for the full design, including how
session state is shared across pages and how the dashboard is verified
with Streamlit's AppTest harness (tests/test_dashboard_pages.py) rather
than just a manual smoke test.
