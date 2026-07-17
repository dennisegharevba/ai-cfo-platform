"""
DataSource: abstract base class every connector must implement.

A connector's only job is to fetch raw data and hand back a plain dict/DataFrame
plus a provider timestamp. It must NOT decide whether the data is "good enough" —
that judgment belongs to the DataIntegrityManager (see refresh_manager.py) and
core.quality.score_quality, so scoring stays consistent across every connector.
"""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any, Optional


class DataSourceError(Exception):
    """Raised by a connector when a fetch fails outright (network, auth, parse)."""


class DataSource(abc.ABC):
    """
    Subclass this for every data provider (FRED, Yahoo Finance, CFTC COT, EIA, ...).

    Required class attributes:
        name            -- short unique id, e.g. "FRED", "YAHOO", "CFTC_COT"
        default_ttl_seconds -- how long a fetched dataset stays fresh
        is_backup       -- True if this connector is a fallback for another
    """

    name: str = "UNSET"
    default_ttl_seconds: int = 300
    is_backup: bool = False

    @abc.abstractmethod
    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        """
        Fetch raw data.

        Returns:
            (payload, provider_timestamp)
            payload: the raw data (dict, list, DataFrame, ...)
            provider_timestamp: the UTC datetime the provider says the data is
                "as of" (e.g. the COT report date, the FRED observation date).
                Return None if the provider doesn't expose one.

        Raises:
            DataSourceError on any failure (network, auth, malformed response).
        """
        raise NotImplementedError

    def validate_shape(self, payload: Any) -> bool:
        """
        Cheap sanity check specific to this connector's expected payload shape.
        Override in subclasses (e.g. "does this dict have the keys I expect").
        Default: any non-empty payload passes.
        """
        if payload is None:
            return False
        if hasattr(payload, "__len__"):
            return len(payload) > 0
        return True
