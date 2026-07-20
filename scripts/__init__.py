"""
scripts/ — demo scripts (Phases 1-9, run manually) and
run_daily_cycle.py (Phase 11's scheduled automation entry point).

This __init__.py exists so tests/test_run_daily_cycle.py can import
run_cycle() and DEPARTMENT_RUNNERS directly rather than only being able to
exercise the script via subprocess — the demo scripts don't need this
since nothing imports them as a module, only run_daily_cycle.py's testable
core required it.
"""
