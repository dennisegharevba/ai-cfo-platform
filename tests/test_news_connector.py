from unittest.mock import patch, MagicMock

import pytest

from connectors.news_connector import NewsRssConnector
from core.data_source import DataSourceError

SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Fake Market News</title>
    <item><title>Stocks rally as tech earnings beat expectations</title></item>
    <item><title>Oil prices slump on demand fears</title></item>
    <item><title>Fed holds rates steady, markets shrug</title></item>
  </channel>
</rss>"""


def _mock_response(text_bytes, status_ok=True):
    resp = MagicMock()
    resp.content = text_bytes
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_parses_headlines_from_rss():
    with patch("connectors.news_connector.requests.get", return_value=_mock_response(SAMPLE_RSS.encode())):
        connector = NewsRssConnector("http://fake.feed/rss")
        payload, provider_ts = connector.fetch()

    assert payload["count"] == 3
    assert "Stocks rally" in payload["headlines"][0]
    assert provider_ts is not None


def test_fetch_respects_max_headlines():
    many_items = "".join(f"<item><title>Headline {i}</title></item>" for i in range(30))
    rss = f"<rss><channel>{many_items}</channel></rss>"
    with patch("connectors.news_connector.requests.get", return_value=_mock_response(rss.encode())):
        connector = NewsRssConnector("http://fake.feed/rss", max_headlines=5)
        payload, _ = connector.fetch()
    assert payload["count"] == 5


def test_invalid_xml_raises():
    with patch("connectors.news_connector.requests.get", return_value=_mock_response(b"not xml at all <<<")):
        connector = NewsRssConnector("http://fake.feed/rss")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_empty_feed_raises():
    rss = "<rss><channel></channel></rss>"
    with patch("connectors.news_connector.requests.get", return_value=_mock_response(rss.encode())):
        connector = NewsRssConnector("http://fake.feed/rss")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_validate_shape():
    connector = NewsRssConnector("http://fake.feed/rss")
    assert connector.validate_shape({"headlines": ["a"]}) is True
    assert connector.validate_shape({"headlines": []}) is False
