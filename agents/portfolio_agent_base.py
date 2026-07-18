"""
PortfolioAgent: the multi-asset counterpart to BaseAgent.

Every prior agent (Phases 2-5) is a BaseAgent: fetch a small FIXED set of
dataset keys, gate on is_usable(), analyze one asset/theme. The Chief Risk
Officer breaks that shape — it needs one price-history dataset PER POSITION
in an arbitrary, caller-supplied Portfolio, and its output isn't about one
asset at all (it's about the portfolio as a whole: concentration,
correlation, portfolio VaR).

Rather than stretch BaseAgent's `required_dataset_keys() -> List[str]`
contract to cover a variable, portfolio-shaped fetch list, this is a
parallel template method with the same non-negotiable rule (never analyze
a dataset that isn't `is_usable()`) but keyed by symbol and driven by a
Portfolio instead of a single asset_or_theme string.
"""

from __future__ import annotations

import abc
import logging
from typing import Dict, List

from core.dataset import Dataset
from core.refresh_manager import DataIntegrityManager
from models.portfolio import Portfolio
from models.report import AgentReport

logger = logging.getLogger("ai_cfo.agents.portfolio")


class PortfolioAgent(abc.ABC):
    department: str = "UNSET"

    def __init__(self, manager: DataIntegrityManager, min_quality: float = 60.0):
        self.manager = manager
        self.min_quality = min_quality

    @abc.abstractmethod
    def price_history_key_for(self, symbol: str) -> str:
        """Map a position's symbol to the DataIntegrityManager key its price history was registered under."""
        raise NotImplementedError

    @abc.abstractmethod
    def _build_report(self, usable_by_symbol: Dict[str, Dataset], portfolio: Portfolio) -> AgentReport:
        """
        Produce the AgentReport using only the per-symbol datasets in
        `usable_by_symbol` (already gated by is_usable()). A symbol missing
        from this dict was blocked (stale/missing/failed validation) and
        must be excluded from any calculation, not silently treated as zero.
        """
        raise NotImplementedError

    def analyze_portfolio(self, portfolio: Portfolio) -> AgentReport:
        """
        Template method: fetch each position's price history through the
        integrity manager, gate on is_usable(), hand only the usable subset
        (keyed by symbol) to the subclass. The ONLY entry point this agent
        type should be called through.
        """
        usable_by_symbol: Dict[str, Dataset] = {}
        gaps: List[str] = []

        for position in portfolio.positions:
            key = self.price_history_key_for(position.symbol)
            try:
                dataset = self.manager.get(key)
            except KeyError:
                logger.error("%s: no data source registered for '%s' (symbol %s)",
                             self.department, key, position.symbol)
                gaps.append(f"{key} (not registered)")
                continue

            if dataset.is_usable(min_quality=self.min_quality):
                usable_by_symbol[position.symbol] = dataset
            else:
                logger.warning(
                    "%s: dataset '%s' for symbol %s is not usable (status=%s, quality=%.1f) — excluded",
                    self.department, key, position.symbol, dataset.validation_status.value, dataset.quality_score,
                )
                gaps.append(f"{key} ({dataset.validation_status.value})")

        report = self._build_report(usable_by_symbol, portfolio)
        report.data_gaps = list(dict.fromkeys(report.data_gaps + gaps))
        return report
