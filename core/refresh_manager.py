"""
DataIntegrityManager: the mandatory gateway between raw data sources and every
analytical agent in the platform.

Responsibilities (per platform spec):
    - Collect live data before every analysis
    - Never let agents use stale data
    - Timestamp every dataset
    - Auto-refresh expired data
    - Fail over to a backup source if the primary fails
    - Score data quality
    - Block recommendations when critical data is unavailable
    - Log every refresh event
    - Cache data only within predefined TTL limits

Usage:
    manager = DataIntegrityManager()
    manager.register("FRED_CPI", primary=FredConnector(series_id="CPIAUCSL"), ttl_seconds=300)
    manager.register("FRED_CPI", backup=SomeOtherConnector(), is_backup=True)

    dataset = manager.get("FRED_CPI")   # fetches or serves cache, always integrity-checked
    if not dataset.is_usable():
        raise StaleDataError(...)       # agent must handle / skip this analysis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .data_source import DataSource, DataSourceError
from .dataset import Dataset, ValidationStatus
from .quality import score_quality

logger = logging.getLogger("ai_cfo.data_integrity")


class StaleDataError(Exception):
    """Raised when the manager cannot produce a usable (non-stale) dataset."""


@dataclass
class _Registration:
    key: str
    primary: DataSource
    backups: List[DataSource] = field(default_factory=list)
    ttl_seconds: Optional[int] = None  # override; else use connector's default


class DataIntegrityManager:
    """
    Central registry + cache + refresh orchestrator.

    One instance should be shared across the whole platform (or one per
    process in a multi-process deployment) so caching is meaningful.
    """

    def __init__(self, min_quality_threshold: float = 60.0):
        self._registrations: Dict[str, _Registration] = {}
        self._cache: Dict[str, Dataset] = {}
        self._refresh_log: List[dict] = []
        self.min_quality_threshold = min_quality_threshold

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(
        self,
        key: str,
        primary: DataSource,
        backups: Optional[List[DataSource]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Register a named dataset with its primary connector and optional backups."""
        self._registrations[key] = _Registration(
            key=key,
            primary=primary,
            backups=backups or [],
            ttl_seconds=ttl_seconds,
        )
        logger.info("Registered dataset '%s' (primary=%s, backups=%s)",
                    key, primary.name, [b.name for b in (backups or [])])

    # ------------------------------------------------------------------ #
    # Core retrieval
    # ------------------------------------------------------------------ #
    def get(self, key: str, force_refresh: bool = False, **fetch_kwargs) -> Dataset:
        """
        Return a Dataset for `key`, refreshing it if the cache is missing/expired
        or if force_refresh=True. Falls back to backup sources on primary failure.

        This method NEVER raises for "stale" data on its own — it always returns
        a Dataset object (possibly marked STALE/MISSING). The caller (an agent)
        MUST check `dataset.is_usable()` before using it. This keeps the contract
        explicit rather than relying on exception control flow for a routine case.
        """
        if key not in self._registrations:
            raise KeyError(f"No data source registered under key '{key}'")

        reg = self._registrations[key]
        cached = self._cache.get(key)

        if not force_refresh and cached is not None and not cached.is_expired():
            return cached

        dataset = self._fetch_with_failover(reg, **fetch_kwargs)
        self._cache[key] = dataset
        self._log_refresh(dataset)
        return dataset

    def get_or_raise(self, key: str, min_quality: Optional[float] = None, **fetch_kwargs) -> Dataset:
        """
        Convenience wrapper for agents that want fail-fast behavior instead of
        manually checking is_usable(). Raises StaleDataError if the data isn't
        usable after a refresh attempt.
        """
        threshold = min_quality if min_quality is not None else self.min_quality_threshold
        dataset = self.get(key, **fetch_kwargs)
        if not dataset.is_usable(min_quality=threshold):
            raise StaleDataError(
                f"Dataset '{key}' is not usable "
                f"(status={dataset.validation_status.value}, "
                f"quality={dataset.quality_score}, "
                f"age={dataset.age_seconds():.0f}s)"
            )
        return dataset

    # ------------------------------------------------------------------ #
    # Internal: fetch + failover + scoring
    # ------------------------------------------------------------------ #
    def _fetch_with_failover(self, reg: _Registration, **fetch_kwargs) -> Dataset:
        now = datetime.now(timezone.utc)
        ttl = reg.ttl_seconds or reg.primary.default_ttl_seconds

        # Try primary first, then each backup in order.
        candidates = [(reg.primary, False)] + [(b, True) for b in reg.backups]
        last_error: Optional[Exception] = None
        last_failed_dataset: Optional[Dataset] = None

        for source, is_backup in candidates:
            try:
                payload, provider_ts = source.fetch(**fetch_kwargs)
                shape_valid = source.validate_shape(payload)
                quality = score_quality(
                    time_collected=now,
                    ttl_seconds=reg.ttl_seconds or source.default_ttl_seconds,
                    is_backup_source=is_backup,
                    shape_valid=shape_valid,
                    now=now,
                )
                status = ValidationStatus.VALID if shape_valid else ValidationStatus.FAILED_VALIDATION
                if is_backup and shape_valid:
                    status = ValidationStatus.DEGRADED

                dataset = Dataset(
                    name=reg.key,
                    payload=payload,
                    source=source.name,
                    time_collected=now,
                    provider_timestamp=provider_ts,
                    cache_expires_at=now + timedelta(seconds=ttl),
                    quality_score=quality,
                    validation_status=status,
                    is_backup_source=is_backup,
                    notes="" if shape_valid else "Failed shape/sanity validation",
                )

                if shape_valid:
                    if is_backup:
                        logger.warning(
                            "Primary source failed for '%s'; served from backup '%s' (quality=%.1f)",
                            reg.key, source.name, quality,
                        )
                    return dataset
                else:
                    logger.error(
                        "Source '%s' returned data for '%s' but it failed validation",
                        source.name, reg.key,
                    )
                    last_error = DataSourceError(f"{source.name} failed shape validation for {reg.key}")
                    last_failed_dataset = dataset

            except DataSourceError as exc:
                logger.error("Source '%s' raised for '%s': %s", source.name, reg.key, exc)
                last_error = exc
                continue

        # Every candidate failed — return a Dataset rather than raising, so the
        # manager's contract (always returns a Dataset) holds. Agents are
        # required to check is_usable() and will correctly refuse to act.
        if last_failed_dataset is not None:
            # At least one source responded but failed shape/sanity validation —
            # surface that diagnosable FAILED_VALIDATION dataset rather than
            # masking it behind a generic MISSING result.
            logger.critical(
                "ALL sources failed for '%s' (last error: %s). Returning failed-validation dataset.",
                reg.key, last_error,
            )
            return last_failed_dataset

        logger.critical(
            "ALL sources failed for '%s' (last error: %s). Data is MISSING.",
            reg.key, last_error,
        )
        return Dataset(
            name=reg.key,
            payload=None,
            source="NONE",
            time_collected=now,
            provider_timestamp=None,
            cache_expires_at=now,
            quality_score=0.0,
            validation_status=ValidationStatus.MISSING,
            notes=f"All sources failed. Last error: {last_error}",
        )

    # ------------------------------------------------------------------ #
    # Logging / audit
    # ------------------------------------------------------------------ #
    def _log_refresh(self, dataset: Dataset) -> None:
        entry = dataset.to_log_dict()
        self._refresh_log.append(entry)
        logger.info("Refreshed '%s': %s", dataset.name, entry)

    @property
    def refresh_log(self) -> List[dict]:
        """Full audit trail of every refresh this manager has performed."""
        return list(self._refresh_log)

    def is_registered(self, key: str) -> bool:
        """Whether a dataset key has already been registered — useful for
        callers (e.g. the dashboard) that register lazily across reruns and
        want to avoid re-registering the same key repeatedly."""
        return key in self._registrations

    def status_report(self) -> List[dict]:
        """Snapshot of every currently cached dataset's integrity status — for the dashboard."""
        report = []
        for key, dataset in self._cache.items():
            report.append({
                **dataset.to_log_dict(),
                "usable_now": dataset.is_usable(min_quality=self.min_quality_threshold),
                "age_seconds": round(dataset.age_seconds(), 1),
            })
        return report
