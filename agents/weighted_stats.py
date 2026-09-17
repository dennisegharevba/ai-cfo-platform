"""
Shared weighted-statistics helpers.

Extracted from agents/chief_strategy_officer.py (where weighted_mean/
weighted_stdev were private module-level functions) now that
agents/fundamental_scoring_engine.py needs the identical "combine several
scored components, weighted by confidence/importance, into one mean plus a
disagreement measure" logic — the same extraction convention already used
for agents/trend_scoring.py (originally from chief_macro_officer.py) and
agents/risk_severity.py (originally from chief_risk_officer.py).

chief_strategy_officer.py imports these directly (aliased back to its old
private names) so none of its own code needed to change.
"""

from __future__ import annotations

from typing import List


def weighted_mean(values: List[float], weights: List[float]) -> float:
    """Weighted arithmetic mean. Returns 0.0 if total weight is zero (no usable inputs)."""
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def weighted_stdev(values: List[float], weights: List[float]) -> float:
    """
    Weighted standard deviation — used across the platform as a
    disagreement/dispersion measure (e.g. "how much do departments/factors
    disagree with each other"), not just a plain statistical spread.
    Returns 0.0 if there's no weight or fewer than 2 values (dispersion is
    undefined with a single point).
    """
    total_weight = sum(weights)
    if total_weight == 0 or len(values) < 2:
        return 0.0
    mean = weighted_mean(values, weights)
    variance = sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total_weight
    return variance ** 0.5
