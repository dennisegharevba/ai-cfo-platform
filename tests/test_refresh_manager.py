from datetime import datetime, timezone

import pytest

from core.data_source import DataSource, DataSourceError
from core.dataset import ValidationStatus
from core.refresh_manager import DataIntegrityManager, StaleDataError


class FakeGoodSource(DataSource):
    """Always succeeds with valid-shaped data."""
    name = "FAKE_GOOD"
    default_ttl_seconds = 300

    def __init__(self, value=42):
        self.value = value
        self.call_count = 0

    def fetch(self, **kwargs):
        self.call_count += 1
        return {"value": self.value}, datetime.now(timezone.utc)

    def validate_shape(self, payload):
        return isinstance(payload, dict) and "value" in payload


class FakeFailingSource(DataSource):
    """Always raises, simulating a dead API / network failure."""
    name = "FAKE_FAILING"
    default_ttl_seconds = 300

    def fetch(self, **kwargs):
        raise DataSourceError("simulated outage")


class FakeMalformedSource(DataSource):
    """Returns data, but it fails shape validation."""
    name = "FAKE_MALFORMED"
    default_ttl_seconds = 300

    def fetch(self, **kwargs):
        return {"unexpected": "shape"}, datetime.now(timezone.utc)

    def validate_shape(self, payload):
        return False


def test_get_returns_usable_dataset_on_primary_success():
    manager = DataIntegrityManager(min_quality_threshold=60)
    manager.register("KEY1", primary=FakeGoodSource())
    ds = manager.get("KEY1")
    assert ds.validation_status == ValidationStatus.VALID
    assert ds.is_usable(min_quality=60) is True
    assert ds.payload["value"] == 42


def test_caching_avoids_refetching_within_ttl():
    source = FakeGoodSource()
    manager = DataIntegrityManager()
    manager.register("KEY1", primary=source, ttl_seconds=300)
    manager.get("KEY1")
    manager.get("KEY1")
    manager.get("KEY1")
    assert source.call_count == 1  # served from cache on 2nd/3rd calls


def test_force_refresh_bypasses_cache():
    source = FakeGoodSource()
    manager = DataIntegrityManager()
    manager.register("KEY1", primary=source, ttl_seconds=300)
    manager.get("KEY1")
    manager.get("KEY1", force_refresh=True)
    assert source.call_count == 2


def test_failover_to_backup_when_primary_fails():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("KEY1", primary=FakeFailingSource(), backups=[FakeGoodSource()])
    ds = manager.get("KEY1")
    assert ds.source == "FAKE_GOOD"
    assert ds.is_backup_source is True
    assert ds.validation_status == ValidationStatus.DEGRADED
    assert ds.is_usable(min_quality=50) is True


def test_all_sources_failing_returns_missing_and_blocks_usage():
    manager = DataIntegrityManager()
    manager.register("KEY1", primary=FakeFailingSource(), backups=[FakeFailingSource()])
    ds = manager.get("KEY1")
    assert ds.validation_status == ValidationStatus.MISSING
    assert ds.is_usable() is False


def test_malformed_payload_fails_validation_and_blocks_usage():
    manager = DataIntegrityManager()
    manager.register("KEY1", primary=FakeMalformedSource())
    ds = manager.get("KEY1")
    assert ds.validation_status == ValidationStatus.FAILED_VALIDATION
    assert ds.is_usable() is False


def test_get_or_raise_raises_stale_data_error_when_unusable():
    manager = DataIntegrityManager()
    manager.register("KEY1", primary=FakeFailingSource())
    with pytest.raises(StaleDataError):
        manager.get_or_raise("KEY1")


def test_get_or_raise_succeeds_when_usable():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("KEY1", primary=FakeGoodSource())
    ds = manager.get_or_raise("KEY1")
    assert ds.payload["value"] == 42


def test_unregistered_key_raises_keyerror():
    manager = DataIntegrityManager()
    with pytest.raises(KeyError):
        manager.get("NOPE")


def test_refresh_log_records_every_refresh():
    manager = DataIntegrityManager()
    manager.register("KEY1", primary=FakeGoodSource())
    manager.get("KEY1")
    manager.get("KEY1", force_refresh=True)
    assert len(manager.refresh_log) == 2


def test_status_report_reflects_cached_datasets():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("KEY1", primary=FakeGoodSource())
    manager.get("KEY1")
    report = manager.status_report()
    assert len(report) == 1
    assert report[0]["name"] == "KEY1"
    assert report[0]["usable_now"] is True
