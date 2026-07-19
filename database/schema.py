"""
SQL schema for the platform's persistence layer (SQLite — free, zero-config,
no external server, part of the Python standard library).

Three tables, matching the spec's "store every report, every alert, every
trade thesis, confidence score, outcome":

    agent_reports     — every individual department's AgentReport
    strategy_reports  — every Chief Strategy Officer synthesis (StrategyReport)
    outcomes          — realized results linked back to a strategy_report,
                        recorded after the fact (this platform never trades
                        automatically, so outcomes are recorded from
                        observed market data, not from any order the
                        platform placed)

List-valued fields (catalysts, risks, evidence, data_gaps, etc.) are stored
as JSON text — SQLite has no native array type, and this keeps the schema
simple and portable rather than introducing a normalized child-table for
what's fundamentally just a list of short strings.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department TEXT NOT NULL,
    asset_or_theme TEXT NOT NULL,
    bias TEXT NOT NULL,
    bias_score REAL NOT NULL,
    confidence REAL NOT NULL,
    risk_level TEXT NOT NULL,
    catalysts TEXT NOT NULL,
    risks TEXT NOT NULL,
    evidence TEXT NOT NULL,
    data_gaps TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_or_theme TEXT NOT NULL,
    overall_market_score REAL NOT NULL,
    confidence_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    bias TEXT NOT NULL,
    bias_score REAL NOT NULL,
    trade_thesis TEXT NOT NULL,
    investment_committee_summary TEXT NOT NULL,
    catalysts TEXT NOT NULL,
    risks TEXT NOT NULL,
    invalidation_notes TEXT NOT NULL,
    contributing_departments TEXT NOT NULL,
    excluded_departments TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_report_id INTEGER NOT NULL,
    realized_return_pct REAL,
    was_correct INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (strategy_report_id) REFERENCES strategy_reports(id)
);

CREATE INDEX IF NOT EXISTS idx_agent_reports_department ON agent_reports(department);
CREATE INDEX IF NOT EXISTS idx_agent_reports_asset ON agent_reports(asset_or_theme);
CREATE INDEX IF NOT EXISTS idx_strategy_reports_asset ON strategy_reports(asset_or_theme);
CREATE INDEX IF NOT EXISTS idx_outcomes_strategy_report ON outcomes(strategy_report_id);
"""
