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
from models.trade_decision import TradeDecision
from models.open_trade import OpenTrade, TradeDirection

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
    # Trade Decision Engine: writes
    # ------------------------------------------------------------------ #
    def save_trade_decision(self, decision: TradeDecision) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO trade_decisions
                (asset_or_theme, fundamental_score, technical_score, risk_score, overall_score,
                 execution_rating, trade_grade, trade_health, institutional_conviction,
                 decision_explanation, key_catalysts, key_risks,
                 contributing_departments, excluded_departments, generated_at, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.asset_or_theme,
                decision.fundamental_score,
                decision.technical_score,
                decision.risk_score,
                decision.overall_score,
                decision.execution_rating.value,
                decision.trade_grade.value,
                decision.trade_health.value,
                decision.institutional_conviction,
                decision.decision_explanation,
                json.dumps(decision.key_catalysts),
                json.dumps(decision.key_risks),
                json.dumps(decision.contributing_departments),
                json.dumps(decision.excluded_departments),
                decision.generated_at.isoformat(),
                _now_iso(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def open_trade(self, trade: OpenTrade) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO open_trades
                (asset_or_theme, direction, entry_technical_bias_score, entry_fundamental_bias_score,
                 entry_risk_score, entry_market_structure_note, stop_loss_level, entry_price,
                 opened_at, closed_at, close_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.asset_or_theme,
                trade.direction.value,
                trade.entry_technical_bias_score,
                trade.entry_fundamental_bias_score,
                trade.entry_risk_score,
                trade.entry_market_structure_note,
                trade.stop_loss_level,
                trade.entry_price,
                trade.opened_at.isoformat(),
                None,
                "",
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def close_trade(self, trade_id: int, close_reason: str) -> None:
        self._conn.execute(
            "UPDATE open_trades SET closed_at = ?, close_reason = ? WHERE id = ?",
            (_now_iso(), close_reason, trade_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Trade Decision Engine: reads
    # ------------------------------------------------------------------ #
    def get_trade_decisions(self, asset_or_theme: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """
        Newest-first. `limit` defaults high (rather than the 100 used
        elsewhere in this store) because agents/score_momentum.py needs
        enough history to reliably find a reading near each of the 1h/4h/
        24h/weekly lookback windows, not just the most recent handful.
        """
        query = "SELECT * FROM trade_decisions WHERE 1=1"
        params: List[Any] = []
        if asset_or_theme is not None:
            query += " AND asset_or_theme = ?"
            params.append(asset_or_theme)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_trade_decision_dict(row) for row in rows]

    def get_open_trade(self, asset_or_theme: str) -> Optional[Dict[str, Any]]:
        """Most recent still-open trade for this asset, or None."""
        row = self._conn.execute(
            "SELECT * FROM open_trades WHERE asset_or_theme = ? AND closed_at IS NULL ORDER BY id DESC LIMIT 1",
            (asset_or_theme,),
        ).fetchone()
        return dict(row) if row else None

    def get_open_trades(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM open_trades WHERE closed_at IS NULL ORDER BY opened_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

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

    @staticmethod
    def _row_to_trade_decision_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for field in ("key_catalysts", "key_risks", "contributing_departments", "excluded_departments"):
            d[field] = json.loads(d[field])
        return d
