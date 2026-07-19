"""
ReportStore: low-level SQLite persistence for AgentReports, StrategyReports,
and their realized outcomes.

Uses the Python standard library's sqlite3 — no new dependency, no external
database server, free and zero-config, consistent with the rest of this
platform's "free or already-justified" tooling choices.

One connection is held open for the store's lifetime (rather than
reconnecting per call) so that ":memory:" databases work correctly for
tests — SQLite's in-memory databases are connection-scoped, so opening a
new connection per call would silently lose all data between calls.
`check_same_thread=False` is set up front since this store will eventually
be shared across a Streamlit app's request threads (Phase 10) — safe here
because SQLite serializes writes internally and this platform has no
concurrent-write hot path yet.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.report import AgentReport
from models.strategy_report import StrategyReport

from .schema import SCHEMA_SQL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReportStore:
    def __init__(self, db_path: str = "ai_cfo_platform.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def save_agent_report(self, report: AgentReport) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO agent_reports
                (department, asset_or_theme, bias, bias_score, confidence, risk_level,
                 catalysts, risks, evidence, data_gaps, generated_at, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.department,
                report.asset_or_theme,
                report.bias.value,
                report.bias_score,
                report.confidence,
                report.risk_level.value,
                json.dumps(report.catalysts),
                json.dumps(report.risks),
                json.dumps(report.evidence),
                json.dumps(report.data_gaps),
                report.generated_at.isoformat(),
                _now_iso(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def save_strategy_report(self, report: StrategyReport) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO strategy_reports
                (asset_or_theme, overall_market_score, confidence_score, risk_level,
                 bias, bias_score, trade_thesis, investment_committee_summary,
                 catalysts, risks, invalidation_notes,
                 contributing_departments, excluded_departments,
                 generated_at, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.asset_or_theme,
                report.overall_market_score,
                report.confidence_score,
                report.risk_level.value,
                report.bias.value,
                report.bias_score,
                report.trade_thesis,
                report.investment_committee_summary,
                json.dumps(report.catalysts),
                json.dumps(report.risks),
                json.dumps(report.invalidation_notes),
                json.dumps(report.contributing_departments),
                json.dumps(report.excluded_departments),
                report.generated_at.isoformat(),
                _now_iso(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def record_outcome(
        self,
        strategy_report_id: int,
        realized_return_pct: Optional[float] = None,
        was_correct: Optional[bool] = None,
        notes: str = "",
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO outcomes (strategy_report_id, realized_return_pct, was_correct, notes, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                strategy_report_id,
                realized_return_pct,
                None if was_correct is None else int(was_correct),
                notes,
                _now_iso(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get_agent_reports(
        self, department: Optional[str] = None, asset_or_theme: Optional[str] = None, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM agent_reports WHERE 1=1"
        params: List[Any] = []
        if department is not None:
            query += " AND department = ?"
            params.append(department)
        if asset_or_theme is not None:
            query += " AND asset_or_theme = ?"
            params.append(asset_or_theme)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_agent_report_dict(row) for row in rows]

    def get_strategy_reports(self, asset_or_theme: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM strategy_reports WHERE 1=1"
        params: List[Any] = []
        if asset_or_theme is not None:
            query += " AND asset_or_theme = ?"
            params.append(asset_or_theme)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_strategy_report_dict(row) for row in rows]

    def get_outcomes(self, strategy_report_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if strategy_report_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM outcomes WHERE strategy_report_id = ? ORDER BY id DESC",
                (strategy_report_id,),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM outcomes ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Row -> dict helpers (JSON fields parsed back into lists)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_agent_report_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for field in ("catalysts", "risks", "evidence", "data_gaps"):
            d[field] = json.loads(d[field])
        return d

    @staticmethod
    def _row_to_strategy_report_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for field in ("catalysts", "risks", "invalidation_notes", "contributing_departments", "excluded_departments"):
            d[field] = json.loads(d[field])
        return d
