from datetime import datetime, timedelta, timezone

from core.dataset import Dataset, ValidationStatus


def _make_dataset(quality=90.0, status=ValidationStatus.VALID, ttl_seconds=300, age_seconds=0):
    now = datetime.now(timezone.utc)
    collected = now - timedelta(seconds=age_seconds)
    return Dataset(
        name="TEST",
        payload={"value": 1},
        source="TESTSRC",
        time_collected=collected,
        provider_timestamp=collected,
        cache_expires_at=collected + timedelta(seconds=ttl_seconds),
        quality_score=quality,
        validation_status=status,
    )


def test_fresh_valid_high_quality_is_usable():
    ds = _make_dataset(quality=95, status=ValidationStatus.VALID, ttl_seconds=300, age_seconds=10)
    assert ds.is_usable(min_quality=60) is True


def test_expired_dataset_is_not_usable():
    ds = _make_dataset(quality=95, status=ValidationStatus.VALID, ttl_seconds=60, age_seconds=120)
    assert ds.is_expired() is True
    assert ds.is_usable(min_quality=60) is False


def test_low_quality_dataset_is_not_usable():
    ds = _make_dataset(quality=40, status=ValidationStatus.VALID, ttl_seconds=300, age_seconds=5)
    assert ds.is_usable(min_quality=60) is False


def test_missing_dataset_is_never_usable_regardless_of_quality():
    ds = _make_dataset(quality=100, status=ValidationStatus.MISSING, ttl_seconds=300, age_seconds=0)
    assert ds.is_usable(min_quality=0) is False


def test_failed_validation_dataset_is_never_usable():
    ds = _make_dataset(quality=100, status=ValidationStatus.FAILED_VALIDATION, ttl_seconds=300, age_seconds=0)
    assert ds.is_usable(min_quality=0) is False


def test_to_log_dict_has_required_fields():
    ds = _make_dataset()
    log = ds.to_log_dict()
    for field in ("name", "source", "time_collected", "cache_expires_at", "quality_score", "validation_status"):
        assert field in log
