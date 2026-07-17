"""
BaseAgent: the shared contract every Chief Officer agent must follow.

The single hard rule (per the platform spec): an agent may NEVER produce a
directional call using data that isn't `is_usable()`. This base class makes
that structurally hard to violate — `analyze()` is a template method that
requires subclasses to declare their required datasets up front, fetches
them all through the DataIntegrityManager, and only calls the subclass's
`_build_report()` with the datasets that passed the integrity gate. Datasets
that didn't pass are recorded as `data_gaps` on the resulting report rather
than silently omitted.
"""

from __future__ import annotations

import abc
import logging
from typing import Dict, List

from core.dataset import Dataset
from core.refresh_manager import DataIntegrityManager
from models.report import AgentReport

logger = logging.getLogger("ai_cfo.agents")


class BaseAgent(abc.ABC):
    department: str = "UNSET"

    def __init__(self, manager: DataIntegrityManager, min_quality: float = 60.0):
        self.manager = manager
        self.min_quality = min_quality

    @abc.abstractmethod
    def required_dataset_keys(self) -> List[str]:
        """Return the list of DataIntegrityManager keys this agent needs to run."""
        raise NotImplementedError

    @abc.abstractmethod
    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        """
        Produce the AgentReport using only the datasets in `usable` (already
        gated by is_usable()). Subclasses must handle the case where a
        dataset they'd like is absent from `usable` (it was blocked) and
        should reduce confidence / widen data_gaps accordingly rather than
        crash.
        """
        raise NotImplementedError

    def analyze(self, asset_or_theme: str) -> AgentReport:
        """
        Template method: fetch every required dataset through the integrity
        manager, gate on is_usable(), and hand only the usable subset to the
        subclass. This is the ONLY entry point agents should be called through.
        """
        usable: Dict[str, Dataset] = {}
        gaps: List[str] = []

        for key in self.required_dataset_keys():
            try:
                dataset = self.manager.get(key)
            except KeyError:
                logger.error("%s: no data source registered for required key '%s'", self.department, key)
                gaps.append(f"{key} (not registered)")
                continue

            if dataset.is_usable(min_quality=self.min_quality):
                usable[key] = dataset
            else:
                logger.warning(
                    "%s: dataset '%s' is not usable (status=%s, quality=%.1f) — excluded from analysis",
                    self.department, key, dataset.validation_status.value, dataset.quality_score,
                )
                gaps.append(f"{key} ({dataset.validation_status.value})")

        report = self._build_report(usable, asset_or_theme)
        # Merge in any gaps the template method found, in addition to whatever
        # the subclass itself flagged.
        report.data_gaps = list(dict.fromkeys(report.data_gaps + gaps))  # de-dupe, preserve order
        return report
