"""
News RSS connector — free, no API key, parses a public market-news RSS feed
using the standard library's XML parser (no extra dependency).

Used by the Chief Sentiment Officer for headline-based sentiment scoring
(see agents/sentiment_scoring.py). The feed URL is configurable (see
config/settings.py's NEWS_RSS_URL) — the default is MarketWatch's public
top-stories feed, a commonly used freely-accessible example feed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from core.data_source import DataSource, DataSourceError


class NewsRssConnector(DataSource):
    name = "NEWS_RSS"
    default_ttl_seconds = 60  # per spec: news refreshed every minute

    def __init__(self, feed_url: str, max_headlines: int = 20, timeout: int = 10):
        self.feed_url = feed_url
        self.max_headlines = max_headlines
        self.timeout = timeout

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        try:
            resp = requests.get(self.feed_url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DataSourceError(f"News RSS request failed for {self.feed_url}: {exc}") from exc

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            raise DataSourceError(f"News RSS feed returned invalid XML: {exc}") from exc

        items = root.findall("./channel/item")
        headlines = []
        for item in items[: self.max_headlines]:
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                headlines.append(title_el.text.strip())

        if not headlines:
            raise DataSourceError(f"News RSS feed returned no headlines from {self.feed_url}")

        payload = {
            "feed_url": self.feed_url,
            "headlines": headlines,
            "count": len(headlines),
        }
        # RSS feeds don't reliably expose a single "as of" timestamp we can
        # trust across providers; treat fetch time as the provider timestamp.
        provider_ts = datetime.now(timezone.utc)
        return payload, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        return isinstance(payload.get("headlines"), list) and len(payload["headlines"]) > 0
