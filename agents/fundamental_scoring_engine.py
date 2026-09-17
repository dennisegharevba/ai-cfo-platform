"""
Institutional Fundamental Scoring Engine — core aggregation logic.

Per the upgrade spec: every factor is evaluated INDEPENDENTLY (its own
score, confidence, importance weight) before contributing to a
category-level score. This module is the generic aggregation step, usable
by any category (Macro first; Commodity Fundamentals, Sentiment, Risk,
Seasonality follow in later phases using this same function — no new
aggregation logic needed per category).

Deliberately reuses the exact same weighted-mean + weighted-disagreement
pattern agents.chief_strategy_officer.ChiefStrategyOfficer already uses to
combine departments (via the newly-shared agents/weighted_stats.py) —
"combine several independently-scored things, weighted by how much to
trust each one, into one score plus a measure of how much they disagree"
is the same operation whether the "things" are departments or individual
fundamental factors, and using one proven implementation for both is more
trustworthy than inventing a second formula that happens to look similar.
"""

from __future__ import annotations

from typing import List

from models.fundamental_factor import CategoryScore, FundamentalFactor
from models.report import Bias, RiskLevel, bias_from_score

from .weighted_stats import weighted_mean, weighted_stdev

# A category's disagreement (weighted stdev across its factors' scores)
# above this threshold bumps risk_level to ELEVATED — factors within one
# category pulling in sharply different directions is itself a risk
# signal, the same principle used for cross-department disagreement in
# ChiefStrategyOfficer.
HIGH_DISAGREEMENT_THRESHOLD = 45.0


def score_category(category: str, factors: List[FundamentalFactor]) -> CategoryScore:
    """
    Combine every factor's own (score, confidence, importance_weight) into
    one category-level score/confidence/bias/risk_level.

    Each factor's effective weight is importance_weight * (confidence/100)
    — the same "weight scaled by how much to trust this input" pattern
    ChiefStrategyOfficer uses for departments (a factor with high
    importance but 0 confidence, e.g. missing data, contributes nothing).

    Returns a CategoryScore with category_score=0.0, category_confidence=0.0,
    bias=NEUTRAL for an empty factor list or when every factor has zero
    effective weight (e.g. all missing data) — never fabricates a
    conclusion from nothing.
    """
    scores: List[float] = []
    weights: List[float] = []
    confidences: List[float] = []

    for factor in factors:
        effective_weight = factor.importance_weight * (factor.confidence / 100.0)
        if effective_weight > 0:
            scores.append(factor.score)
            weights.append(effective_weight)
            confidences.append(factor.confidence)

    if not scores:
        return CategoryScore(
            category=category, factors=factors,
            category_score=0.0, category_confidence=0.0,
            bias=Bias.NEUTRAL, risk_level=RiskLevel.HIGH, disagreement=0.0,
        )

    category_score = weighted_mean(scores, weights)
    disagreement = weighted_stdev(scores, weights)
    # Confidence is the weighted average of contributing factors' own
    # confidence, penalized by disagreement — same shape as
    # ChiefStrategyOfficer's department-level confidence calculation.
    avg_confidence = weighted_mean(confidences, weights)
    penalty = min(30.0, disagreement * 0.3)
    category_confidence = max(0.0, avg_confidence - penalty)

    risk_level = RiskLevel.ELEVATED if disagreement >= HIGH_DISAGREEMENT_THRESHOLD else RiskLevel.MODERATE

    return CategoryScore(
        category=category,
        factors=factors,
        category_score=round(category_score, 1),
        category_confidence=round(category_confidence, 1),
        bias=bias_from_score(category_score),
        risk_level=risk_level,
        disagreement=round(disagreement, 1),
    )
