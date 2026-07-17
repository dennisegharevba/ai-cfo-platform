from datetime import datetime, timezone
from typing import Dict, List

from agents.base_agent import BaseAgent
from core.data_source import DataSource, DataSourceError
from core.refresh_manager import DataIntegrityManager
from models.report import AgentReport, Bias, RiskLevel


class FakeSource(DataSource):
    name = "FAKE"
    default_ttl_seconds = 300

    def __init__(self, payload=None, should_fail=False):
        self.payload = payload or {"value": 1}
        self.should_fail = should_fail

    def fetch(self, **kwargs):
        if self.should_fail:
            raise DataSourceError("simulated failure")
        return self.payload, datetime.now(timezone.utc)


class DummyAgent(BaseAgent):
    """Minimal concrete agent for exercising the BaseAgent contract in isolation."""
    department = "Dummy Agent"

    def required_dataset_keys(self) -> List[str]:
        return ["KEY_A", "KEY_B"]

    def _build_report(self, usable: Dict, asset_or_theme: str) -> AgentReport:
        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=Bias.NEUTRAL,
            bias_score=0.0,
            confidence=100.0 if len(usable) == 2 else 50.0,
            risk_level=RiskLevel.LOW,
            evidence=[f"saw {len(usable)} usable datasets"],
        )


def test_agent_receives_all_datasets_when_all_usable():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("KEY_A", primary=FakeSource())
    manager.register("KEY_B", primary=FakeSource())
    agent = DummyAgent(manager)
    report = agent.analyze("Test Theme")
    assert report.confidence == 100.0
    assert report.data_gaps == []


def test_agent_excludes_and_flags_unregistered_key():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("KEY_A", primary=FakeSource())
    # KEY_B intentionally never registered
    agent = DummyAgent(manager)
    report = agent.analyze("Test Theme")
    assert report.confidence == 50.0
    assert any("KEY_B" in gap for gap in report.data_gaps)
    assert report.is_degraded() is True


def test_agent_excludes_and_flags_failed_source():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("KEY_A", primary=FakeSource())
    manager.register("KEY_B", primary=FakeSource(should_fail=True))
    agent = DummyAgent(manager)
    report = agent.analyze("Test Theme")
    assert report.confidence == 50.0
    assert any("KEY_B" in gap and "missing" in gap for gap in report.data_gaps)


def test_never_degraded_report_has_empty_gaps():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("KEY_A", primary=FakeSource())
    manager.register("KEY_B", primary=FakeSource())
    agent = DummyAgent(manager)
    report = agent.analyze("Test Theme")
    assert report.is_degraded() is False
