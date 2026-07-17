"""
Dataset: the mandatory metadata envelope for every piece of data that flows
through the platform.

Per the platform spec, every dataset MUST carry:
    - source                (which provider / connector produced it)
    - time_collected        (when *we* fetched it, UTC)
    - provider_timestamp    (when the provider says the data is *as of*)
    - cache_expires_at      (TTL cutoff — after this, the data is stale)
    - quality_score         (0-100, see core.quality)
    - validation_status     (ValidationStatus enum)

Agents (Chief Macro Officer, Chief Commodity Analyst, etc.) must never touch
`Dataset.payload` directly without first calling `Dataset.is_usable()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ValidationStatus(str, Enum):
    VALID = "valid"                # passed all checks, safe to use
    STALE = "stale"                 # past cache_expires_at
    DEGRADED = "degraded"           # served from a backup/secondary source
    FAILED_VALIDATION = "failed"    # shape/sanity checks failed
    MISSING = "missing"             # no data could be retrieved at all


@dataclass
class Dataset:
    """A single fetched payload plus its full integrity metadata."""

    name: str                              # e.g. "CFTC_COT_GOLD", "FRED_CPI"
    payload: Any                            # the actual data (dict/DataFrame/etc.)
    source: str                             # provider name, e.g. "FRED", "CFTC_COT"
    time_collected: datetime                # UTC, when our system fetched it
    provider_timestamp: Optional[datetime]  # UTC, the "as of" date from the provider
    cache_expires_at: datetime              # UTC, TTL cutoff
    quality_score: float = 0.0              # 0-100
    validation_status: ValidationStatus = ValidationStatus.MISSING
    is_backup_source: bool = False
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self.cache_expires_at

    def is_usable(self, min_quality: float = 60.0, now: Optional[datetime] = None) -> bool:
        """
        The single gate every agent must call before using a dataset.

        Returns False if the data is expired, failed validation, missing,
        or below the minimum acceptable quality score.
        """
        if self.validation_status in (ValidationStatus.FAILED_VALIDATION, ValidationStatus.MISSING):
            return False
        if self.is_expired(now):
            return False
        if self.quality_score < min_quality:
            return False
        return True

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.time_collected).total_seconds()

    def to_log_dict(self) -> dict:
        """Compact representation for the refresh/audit log."""
        return {
            "name": self.name,
            "source": self.source,
            "time_collected": self.time_collected.isoformat(),
            "provider_timestamp": self.provider_timestamp.isoformat() if self.provider_timestamp else None,
            "cache_expires_at": self.cache_expires_at.isoformat(),
            "quality_score": self.quality_score,
            "validation_status": self.validation_status.value,
            "is_backup_source": self.is_backup_source,
        }
