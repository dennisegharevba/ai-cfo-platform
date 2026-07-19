"""
database/ — persistence layer for the Chief Learning Officer (Phase 8).

SQLite-based, free and zero-config (Python standard library only).
See schema.py for the table definitions and report_store.py for the
ReportStore class that reads/writes them. agents/chief_learning_officer.py
wraps ReportStore with the higher-level performance-analytics methods the
spec calls for.
"""

from .report_store import ReportStore

__all__ = ["ReportStore"]
