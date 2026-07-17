"""
Quality scoring for fetched datasets.

The score (0-100) is a simple, auditable weighted combination of:
    - freshness   : how much of the TTL window has been consumed
    - source tier : primary source vs. backup/secondary source
    - shape check : did the connector's validate_shape() pass

This is intentionally simple and transparent rather than a black box —
institutional research pipelines need every score to be explainable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# Weights must sum to 100
WEIGHT_FRESHNESS = 50
WEIGHT_SOURCE_TIER = 30
WEIGHT_SHAPE_VALID = 20


def score_quality(
    *,
    time_collected: datetime,
    ttl_seconds: int,
    is_backup_source: bool,
    shape_valid: bool,
    now: Optional[datetime] = None,
) -> float:
    """
    Compute a 0-100 quality score for a freshly fetched dataset.

    freshness_score: 100 if just collected, decaying linearly to 0 at TTL expiry.
    source_tier_score: 100 for a primary source, 60 for a backup/secondary source.
    shape_score: 100 if the connector's shape/sanity check passed, else 0.
    """
    now = now or datetime.now(timezone.utc)
    age = max(0.0, (now - time_collected).total_seconds())
    ttl_seconds = max(ttl_seconds, 1)

    freshness_fraction = max(0.0, 1.0 - (age / ttl_seconds))
    freshness_score = freshness_fraction * 100

    source_tier_score = 60.0 if is_backup_source else 100.0
    shape_score = 100.0 if shape_valid else 0.0

    total = (
        (freshness_score * WEIGHT_FRESHNESS)
        + (source_tier_score * WEIGHT_SOURCE_TIER)
        + (shape_score * WEIGHT_SHAPE_VALID)
    ) / 100.0

    return round(total, 2)
