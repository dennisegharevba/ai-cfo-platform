"""
Core module: Data Integrity & Refresh Manager.

This is the foundational layer of the AI Chief Fundamental Officer platform.
No analytical agent is permitted to consume data that has not passed through
this layer. See docs/ARCHITECTURE.md for the full design rationale.
"""

from .dataset import Dataset, ValidationStatus
from .data_source import DataSource, DataSourceError
from .quality import score_quality
from .refresh_manager import DataIntegrityManager, StaleDataError

__all__ = [
    "Dataset",
    "ValidationStatus",
    "DataSource",
    "DataSourceError",
    "score_quality",
    "DataIntegrityManager",
    "StaleDataError",
]
