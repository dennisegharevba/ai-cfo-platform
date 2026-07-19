"""
Dashboard smoke tests using Streamlit's official AppTest harness
(streamlit.testing.v1) — this actually EXECUTES each page's Python code in
a test runtime and surfaces any exception, unlike a plain HTTP GET to a
page route (which can return 200 without the script ever truly running,
under Streamlit's client-side page routing).

These tests intentionally run with NO network access available (same as
this repo's CI runners) — every page must degrade gracefully (showing
blocked/zero-confidence results, per every phase's data-integrity design)
rather than crash when a data source is unreachable.
"""

import pytest
from streamlit.testing.v1 import AppTest

PAGES = [
    "dashboard/Home.py",
    "dashboard/pages/1_Data_Health.py",
    "dashboard/pages/2_Department_Reports.py",
    "dashboard/pages/3_Strategy_Synthesis.py",
    "dashboard/pages/4_Risk_Officer.py",
    "dashboard/pages/5_Performance_Learning.py",
    "dashboard/pages/6_Alerts_Execution.py",
]


@pytest.mark.parametrize("page_path", PAGES)
def test_page_renders_without_exception(page_path):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.run()
    assert not at.exception, f"{page_path} raised: {at.exception}"


def test_data_health_refresh_button_does_not_crash_offline():
    """Clicking 'Refresh all data sources now' with no network available
    must degrade gracefully (blocked/missing datasets), never crash — this
    is the same integrity-manager contract every prior phase relies on."""
    at = AppTest.from_file("dashboard/pages/1_Data_Health.py", default_timeout=30)
    at.run()
    at.button[0].click().run()
    assert not at.exception


def test_department_reports_run_button_does_not_crash_offline():
    """Running Chief Macro Officer (the default selection) with no network
    available must degrade to a low-confidence report, never crash."""
    at = AppTest.from_file("dashboard/pages/2_Department_Reports.py", default_timeout=30)
    at.run()
    at.button[0].click().run()
    assert not at.exception


def test_risk_officer_run_button_does_not_crash_offline():
    at = AppTest.from_file("dashboard/pages/4_Risk_Officer.py", default_timeout=30)
    at.run()
    at.button[0].click().run()
    assert not at.exception


def test_strategy_synthesis_with_empty_pool_shows_info_not_crash():
    at = AppTest.from_file("dashboard/pages/3_Strategy_Synthesis.py", default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.info) >= 1  # "no reports yet" message, not a crash


def test_alerts_execution_with_no_strategy_report_shows_info_not_crash():
    at = AppTest.from_file("dashboard/pages/6_Alerts_Execution.py", default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.info) >= 1
