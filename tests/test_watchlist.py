"""
Tests for config/watchlist.py — specifically locking in the
"risk_fundamentals" coverage across every asset class (commodities,
currency/FX, equities, crypto), per an explicit request to extend risk
coverage beyond commodities alone. These are separate from
tests/test_run_daily_cycle.py's existing "every department key has a
real handler" check, which proves the wiring is *structurally* valid but
wouldn't catch a future change that silently narrowed coverage back down
(e.g. someone removing a ticker from FX_YAHOO_TICKERS) — these tests
assert the actual counts/coverage directly.
"""

from config.watchlist import (
    WATCHLIST_DAILY, WATCHLIST_WEEKLY,
    COMMODITY_YAHOO_TICKERS, FX_YAHOO_TICKERS, CRYPTO_YAHOO_TICKERS,
)


def _entry(asset_or_theme):
    return next(e for e in WATCHLIST_DAILY if e["asset_or_theme"] == asset_or_theme)


def test_every_fx_pair_with_a_known_yahoo_ticker_has_risk_fundamentals():
    for display_name, yahoo_ticker in FX_YAHOO_TICKERS.items():
        entry = _entry(display_name)
        assert "risk_fundamentals" in entry["departments"], f"{display_name} is missing risk_fundamentals"
        assert entry["departments"]["risk_fundamentals"]["ticker"] == yahoo_ticker


def test_every_commodity_with_a_known_yahoo_ticker_has_risk_fundamentals():
    for display_name, yahoo_ticker in COMMODITY_YAHOO_TICKERS.items():
        entry = _entry(display_name)
        assert "risk_fundamentals" in entry["departments"], f"{display_name} is missing risk_fundamentals"
        assert entry["departments"]["risk_fundamentals"]["ticker"] == yahoo_ticker


def test_btc_has_risk_fundamentals_wired():
    entry = _entry("BTC")
    assert entry["departments"]["risk_fundamentals"]["ticker"] == CRYPTO_YAHOO_TICKERS["BTC"]
    assert "crypto" in entry["departments"]  # the original department is still there, not replaced


def test_every_equity_ticker_has_risk_fundamentals_using_its_own_ticker():
    for entry in WATCHLIST_WEEKLY:
        assert "risk_fundamentals" in entry["departments"], f"{entry['asset_or_theme']} is missing risk_fundamentals"
        assert entry["departments"]["risk_fundamentals"]["ticker"] == entry["asset_or_theme"]
        assert "equity" in entry["departments"]  # the original department is still there, not replaced


def test_equity_watchlist_coverage_is_complete_not_partial():
    from config.sp500_tickers import LARGE_CAP_TICKERS
    covered = sum(1 for e in WATCHLIST_WEEKLY if "risk_fundamentals" in e["departments"])
    assert covered == len(LARGE_CAP_TICKERS)


def test_fx_pairs_without_a_known_yahoo_ticker_do_not_get_a_fabricated_one():
    """Every currently-configured FX pair does have a Yahoo ticker, but
    this test documents and protects the intended behavior for any future
    pair added to config/cftc_markets.py without also being added to
    FX_YAHOO_TICKERS: it should NOT get a fabricated risk_fundamentals
    entry, matching the same 'no ticker, no entry' rule already used for
    commodities."""
    from config.cftc_markets import FX_FUTURES_MARKETS
    for display_name in FX_FUTURES_MARKETS:
        entry = _entry(display_name)
        if display_name not in FX_YAHOO_TICKERS:
            assert "risk_fundamentals" not in entry["departments"]
