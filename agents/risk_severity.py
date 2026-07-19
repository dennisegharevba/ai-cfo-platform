"""
Shared RiskLevel severity ordering, extracted from chief_risk_officer.py
(where it was a private helper) now that agents/chief_strategy_officer.py
needs the identical "combine several risk_level readings into one worst-case
verdict" logic — the same third-consumer-triggers-extraction pattern
documented in docs/ARCHITECTURE_PHASE4.md for agents/trend_scoring.py.
"""

from __future__ import annotations

from models.report import RiskLevel

SEVERITY_ORDER = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.ELEVATED, RiskLevel.HIGH]


def worse_risk_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return whichever of the two RiskLevels is more severe."""
    return a if SEVERITY_ORDER.index(a) >= SEVERITY_ORDER.index(b) else b


def worst_of(levels) -> RiskLevel:
    """Return the most severe RiskLevel in an iterable, defaulting to LOW if empty."""
    result = RiskLevel.LOW
    for level in levels:
        result = worse_risk_level(result, level)
    return result
