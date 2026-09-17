from unittest.mock import patch
from datetime import date, timedelta
import io
import contextlib
import sys

import scripts.run_screener as screener_module


def _flat_history(n=150):
    base = date(2024, 1, 1)
    return [(base + timedelta(days=i), 100.0 + i * 0.15, 1_000_000.0) for i in range(n)]


def test_alpaca_tradeable_asset_classes_is_exactly_equity_and_crypto():
    """The exact set found via research to be correct — if this ever
    needs to change (e.g. Alpaca adds forex support), it should be a
    deliberate, reviewed change to this constant, not a silent drift."""
    assert screener_module.ALPACA_TRADEABLE_ASSET_CLASSES == {"equity", "crypto"}


def test_build_portfolio_excludes_commodity_and_fx_candidates(capsys):
    """
    THE core regression test for a real, critical bug found via live
    testing: --build-portfolio was including commodity and FX candidates
    in the target allocation and rebalance plan, producing orders like
    "NZD/USD BUY 29138.33" — mathematically correct given the dollar
    allocation, but for asset types Alpaca's Trading API cannot trade
    under any circumstances (confirmed via research: equities and crypto
    only, no forex or commodities/futures support). Had --submit been
    used, every one of those orders would have been rejected or worse.
    Proven directly: a mixed-class result must show commodity/FX in the
    RANKING (real, useful signal) but exclude them from the target
    allocation Alpaca could ever be asked to execute.
    """
    with patch.object(screener_module, "_fetch_price_and_volume_history", side_effect=lambda t: _flat_history()), \
         patch.object(screener_module, "LARGE_CAP_TICKERS", ["MSFT"]), \
         patch.object(screener_module, "FX_YAHOO_TICKERS", {"NZD/USD": "NZDUSD=X"}), \
         patch.object(screener_module, "CRYPTO_YAHOO_TICKERS", {"BTC": "BTC-USD"}), \
         patch.object(screener_module, "COMMODITY_YAHOO_TICKERS", {"Wheat": "ZW=F"}), \
         patch("config.settings.ALPACA_API_KEY", ""):
        sys.argv = ["run_screener.py", "--request-delay", "0", "--min-confidence", "0", "--top-n", "10", "--build-portfolio"]
        screener_module.main()

    output = capsys.readouterr().out
    # Commodity/FX still appear in the ranked results — real, useful signal.
    assert "NZD/USD" in output
    assert "Wheat" in output
    # And appear again, with full detail, in a dedicated section for manually
    # trading them elsewhere — not just a bare excluded-names list.
    assert "=== Manual Trading Candidates (2)" in output
    assert "not tradeable via Alpaca" in output

    # The allocation section itself must never mention the excluded assets.
    allocation_start = output.index("=== Building target allocation ===")
    allocation_section = output[allocation_start:]
    assert "NZD/USD" not in allocation_section
    assert "Wheat" not in allocation_section


def test_manual_trading_candidates_show_full_detail_not_just_names():
    """The specific improvement requested: someone who wants to manually
    trade an excluded commodity/FX candidate on another platform needs
    the same bias/confidence/volatility/conviction detail the main
    ranking table shows — not just a bare name, which was the original,
    less useful version of this message."""
    buf = io.StringIO()
    with patch.object(screener_module, "_fetch_price_and_volume_history", side_effect=lambda t: _flat_history()), \
         patch.object(screener_module, "LARGE_CAP_TICKERS", ["MSFT"]), \
         patch.object(screener_module, "FX_YAHOO_TICKERS", {"NZD/USD": "NZDUSD=X"}), \
         patch.object(screener_module, "CRYPTO_YAHOO_TICKERS", {}), \
         patch.object(screener_module, "COMMODITY_YAHOO_TICKERS", {}), \
         patch("config.settings.ALPACA_API_KEY", ""), \
         contextlib.redirect_stdout(buf):
        sys.argv = ["run_screener.py", "--request-delay", "0", "--min-confidence", "0", "--top-n", "10", "--build-portfolio"]
        screener_module.main()

    output = buf.getvalue()
    manual_section = output[output.index("=== Manual Trading Candidates"):]
    nzd_line = next(line for line in manual_section.splitlines() if line.startswith("NZD/USD"))
    # A full detail row has direction, bias, confidence, volatility, and conviction —
    # not just the label. Splitting confirms every column is genuinely present.
    assert len(nzd_line.split()) >= 6


def test_build_portfolio_with_only_tradeable_candidates_shows_no_exclusion_message(capsys):
    with patch.object(screener_module, "_fetch_price_and_volume_history", side_effect=lambda t: _flat_history()), \
         patch.object(screener_module, "LARGE_CAP_TICKERS", ["MSFT", "AAPL"]), \
         patch.object(screener_module, "FX_YAHOO_TICKERS", {}), \
         patch.object(screener_module, "CRYPTO_YAHOO_TICKERS", {}), \
         patch.object(screener_module, "COMMODITY_YAHOO_TICKERS", {}), \
         patch("config.settings.ALPACA_API_KEY", ""):
        sys.argv = ["run_screener.py", "--asset-classes", "equity", "--request-delay", "0", "--min-confidence", "0", "--top-n", "10", "--build-portfolio"]
        screener_module.main()

    output = capsys.readouterr().out
    assert "Manual Trading Candidates" not in output


def test_build_portfolio_with_zero_tradeable_candidates_stops_cleanly(capsys):
    with patch.object(screener_module, "_fetch_price_and_volume_history", side_effect=lambda t: _flat_history()), \
         patch.object(screener_module, "LARGE_CAP_TICKERS", []), \
         patch.object(screener_module, "FX_YAHOO_TICKERS", {"NZD/USD": "NZDUSD=X"}), \
         patch.object(screener_module, "CRYPTO_YAHOO_TICKERS", {}), \
         patch.object(screener_module, "COMMODITY_YAHOO_TICKERS", {"Wheat": "ZW=F"}), \
         patch("config.settings.ALPACA_API_KEY", ""):
        sys.argv = ["run_screener.py", "--request-delay", "0", "--min-confidence", "0", "--top-n", "10", "--build-portfolio"]
        screener_module.main()  # must not raise

    output = capsys.readouterr().out
    assert "nothing to build" in output.lower()
