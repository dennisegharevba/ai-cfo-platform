"""
Run a real backtest: does a signal's historical bias_score correlate with
the asset's actual subsequent price return?

Per docs/ARCHITECTURE_BACKTESTING.md: this validates SIGNALS, not trading
P&L (this platform never places trades). Signals wired in: Seasonality
(zero point-in-time risk), four Institutional Market Regime components
(VIX, Real Yield, Treasury Yield, Fed Policy — all daily market-observed
series, never meaningfully revised), and all 16 of Chief Macro Officer's
own factors (CPI, GDP, Initial Jobless Claims, etc. — see
agents.backtest_signals.MACRO_FACTOR_NAMES for the exact list), added
specifically so the normalization thresholds recalibrated in
docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md can eventually be
validated against real historical data.

Needs real network access and (for everything but Seasonality) a real
FRED_API_KEY — this cannot produce a real answer from this development
sandbox. Every date this script can't get real data for is skipped, not
estimated, so a partial-network-access run will just show a smaller
(honestly labeled) sample size, never a fabricated one.

Run:
    python scripts/run_backtest.py --signal seasonality --asset Gold
    python scripts/run_backtest.py --signal vix --asset SPY
    python scripts/run_backtest.py --signal real_yield --asset GC=F
    python scripts/run_backtest.py --signal treasury_yield --asset SPY
    python scripts/run_backtest.py --signal fed_policy --asset SPY
    python scripts/run_backtest.py --signal "CPI (Headline, YoY)" --asset SPY
    python scripts/run_backtest.py --signal "Initial Jobless Claims" --asset SPY

For a Macro factor, --asset is the asset you're testing the factor's
predictive value AGAINST (e.g. does CPI correlate with S&P500 forward
returns) — a different meaning than for --signal seasonality, where
--asset is the asset the seasonal pattern itself belongs to. Quote any
Macro factor name that contains spaces/parentheses/commas.

Optional: --start YYYY-MM-DD --end YYYY-MM-DD --step-days N --forward-days N
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import FRED_API_KEY, LOG_LEVEL
from config.watchlist import COMMODITY_YAHOO_TICKERS, FX_YAHOO_TICKERS, CRYPTO_YAHOO_TICKERS
from connectors.yahoo_history_connector import YahooHistoryConnector
from core.data_source import DataSourceError
from agents.backtest_engine import run_backtest
from agents.backtest_signals import (
    seasonality_signal, vix_signal, real_yield_signal, treasury_yield_signal, fed_policy_signal,
    macro_factor_signal, MACRO_FACTOR_NAMES,
)

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SIGNAL_FUNCTIONS = {
    "seasonality": lambda d, asset: seasonality_signal(asset, d),
    "vix": lambda d, asset: vix_signal(d, FRED_API_KEY),
    "real_yield": lambda d, asset: real_yield_signal(d, FRED_API_KEY),
    "treasury_yield": lambda d, asset: treasury_yield_signal(d, FRED_API_KEY),
    "fed_policy": lambda d, asset: fed_policy_signal(d, FRED_API_KEY),
}
# All 16 Chief Macro Officer factors, keyed by their exact factor name —
# built directly from MACRO_FACTOR_NAMES so this can never drift out of
# sync with agents.chief_macro_officer._FACTOR_SPECS.
for _factor_name in MACRO_FACTOR_NAMES:
    SIGNAL_FUNCTIONS[_factor_name] = (
        lambda d, asset, _fn=_factor_name: macro_factor_signal(_fn, d, FRED_API_KEY)
    )

# Reused so --asset "Gold" (the Seasonality display name) can auto-resolve
# to a real Yahoo ticker for price fetching, rather than making the user
# supply both the display name AND its ticker separately for the common
# cases this platform already has a mapping for.
_ALL_YAHOO_TICKERS = {**COMMODITY_YAHOO_TICKERS, **FX_YAHOO_TICKERS, **CRYPTO_YAHOO_TICKERS}


def _needs_fred_pacing(signal_name: str) -> bool:
    """Every signal except seasonality makes real FRED requests per test
    date and needs rate-limit pacing between them; seasonality makes none."""
    return signal_name != "seasonality"


def _resolve_price_ticker(asset: str, explicit_ticker: str = None) -> str:
    """Explicit --price-ticker always wins. Otherwise, try the existing
    commodity/FX/crypto Yahoo ticker mappings (asset is a display name
    like "Gold"). Otherwise, assume `asset` IS already a valid Yahoo
    ticker (the case for --signal vix/real_yield/etc., where --asset is
    meant to be a ticker like "SPY" from the start)."""
    if explicit_ticker:
        return explicit_ticker
    return _ALL_YAHOO_TICKERS.get(asset, asset)


def _fetch_raw_history_rows(ticker: str, max_retries: int = 2, retry_delay: float = 2.0) -> list:
    """
    Shared, retrying fetch of the full raw history rows (each a dict with
    date/close/high/low/volume) from YahooHistoryConnector.
    _fetch_price_history() (close-only, the original, widely-used shape)
    and _fetch_price_and_volume_history() (adds volume, for
    agents/opportunity_screener.py's volume confirmation scoring) both
    build on this one retrying fetch, so the retry logic added for the
    intermittent Yahoo failures (see docs/ARCHITECTURE_FETCH_RETRY.md)
    lives in exactly one place, not duplicated.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            payload, _ = YahooHistoryConnector(ticker, period="10y", interval="1d").fetch()
            return payload.get("history", [])
        except DataSourceError as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(retry_delay)
    raise last_error


def _fetch_price_history(ticker: str, max_retries: int = 2, retry_delay: float = 2.0) -> list:
    """
    Fetches ~10 years of daily closes via the existing YahooHistoryConnector
    (unchanged — just a longer period than its live-analysis callers use).

    Parses dates with datetime.fromisoformat() rather than a rigid
    strptime("%Y-%m-%d") format — connectors/yahoo_history_connector.py
    builds its "date" field from a pandas Timestamp's .isoformat(), which
    includes a time component (e.g. "2026-08-05T00:00:00"), not a bare
    date string. strptime with a date-only format silently raised
    ValueError on every single row, and the broad except below silently
    swallowed it — a real bug caught only by actually running this live
    (it produced "0 daily closes" with no error message at all, not a
    crash), fixed here rather than left as a caveat.

    Retries up to max_retries times, retry_delay seconds apart, before
    giving up. Found via live testing across multiple real scans: Yahoo's
    real failures ("possibly delisted" for large, genuinely-listed
    companies like Meta, Starbucks, Synopsys) are intermittent, not
    consistently tied to request rate or scan position — one run failed
    on BTC-USD at position 22, a different run had it succeed; slowing
    the whole scan down did not reliably reduce failures. A brief retry
    on just the failing ticker recovers most of these transient failures
    without needing to slow down every other request in the scan.

    Unchanged return shape: oldest-first (date, close) tuples. The retry
    itself now lives in _fetch_raw_history_rows() above, shared with
    _fetch_price_and_volume_history() below — refactored out, not
    duplicated, when volume support was added.
    """
    rows = _fetch_raw_history_rows(ticker, max_retries=max_retries, retry_delay=retry_delay)
    result = []
    for row in rows:
        try:
            d = datetime.fromisoformat(row["date"]).date()
            result.append((d, float(row["close"])))
        except (KeyError, ValueError, TypeError):
            continue
    result.sort(key=lambda t: t[0])  # oldest first, what agents.backtest_engine expects
    return result


def _fetch_price_and_volume_history(ticker: str, max_retries: int = 2, retry_delay: float = 2.0) -> list:
    """
    Same retrying fetch as _fetch_price_history() above, but also returns
    each day's volume — for agents/opportunity_screener.py's volume
    confirmation scoring specifically. A separate function rather than
    changing _fetch_price_history()'s own return shape, to avoid any risk
    of breaking its existing callers (run_backtest.py, run_backtest_all.py,
    run_full_pipeline.py), which all expect plain (date, close) tuples.

    Returns oldest-first (date, close, volume) tuples. volume is 0.0 when
    Yahoo doesn't report usable volume for an instrument (common for some
    FX pairs) — never fabricated from close price or guessed.
    """
    rows = _fetch_raw_history_rows(ticker, max_retries=max_retries, retry_delay=retry_delay)
    result = []
    for row in rows:
        try:
            d = datetime.fromisoformat(row["date"]).date()
            result.append((d, float(row["close"]), float(row.get("volume", 0.0))))
        except (KeyError, ValueError, TypeError):
            continue
    result.sort(key=lambda t: t[0])
    return result


def main():
    parser = argparse.ArgumentParser(description="Run a signal-vs-forward-return correlation backtest.")
    parser.add_argument("--signal", required=True, choices=list(SIGNAL_FUNCTIONS.keys()))
    parser.add_argument("--asset", required=True, help="For 'seasonality': the display name (e.g. 'Gold'). For "
                                                          "the FRED-based signals: the Yahoo ticker to test forward "
                                                          "returns against (e.g. 'SPY', 'GC=F').")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to 5 years ago")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--step-days", type=int, default=30, help="Spacing between test dates")
    parser.add_argument("--forward-days", type=int, default=20, help="Forward return window")
    parser.add_argument(
        "--price-ticker", default=None,
        help="Yahoo ticker for the price-return side of the backtest, if it differs from --asset "
             "(mainly needed for --signal seasonality, where --asset is a display name like 'Gold' — "
             "auto-resolved to 'GC=F' via config/watchlist.py's existing ticker mappings when possible; "
             "supply this explicitly for anything not in those mappings, e.g. 'S&P500'/'NASDAQ100').",
    )
    parser.add_argument(
        "--request-delay", type=float, default=0.6,
        help="Seconds to pause between historical dates for FRED-based signals (skipped entirely for "
             "--signal seasonality, which makes no network requests). Guards against FRED's rate limit "
             "being hit partway through a run, which silently drops some readings rather than erroring "
             "clearly. Raise this if you still see usable-reading counts vary between identical runs.",
    )
    args = parser.parse_args()

    if args.signal != "seasonality" and not FRED_API_KEY:
        print(f"FRED_API_KEY is not set — the '{args.signal}' signal needs it. Set it in .env and re-run.")
        return

    price_ticker = _resolve_price_ticker(args.asset, args.price_ticker)

    end_date = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else end_date - timedelta(days=365 * 5)

    print(f"\nFetching price history for {price_ticker}"
          + (f" (resolved from --asset '{args.asset}')" if price_ticker != args.asset else "") + "...")
    try:
        price_history = _fetch_price_history(price_ticker)
    except Exception as exc:
        print(f"Could not fetch price history for '{price_ticker}': {exc}")
        print("If this ticker doesn't auto-resolve correctly, try passing --price-ticker explicitly.")
        return
    print(f"  Got {len(price_history)} daily closes.")

    signal_fn = SIGNAL_FUNCTIONS[args.signal]
    test_dates = []
    d = start_date
    while d <= end_date:
        test_dates.append(d)
        d += timedelta(days=args.step_days)

    print(f"\nComputing '{args.signal}' signal for {len(test_dates)} historical dates "
          f"({start_date} to {end_date}, every {args.step_days} days)...")
    signal_scores = []
    # Rate-limit pacing: FRED enforces a real request-per-minute limit per
    # API key. This script fires one signal_fn() call per test date, and
    # some signals (real_yield/treasury_yield/fed_policy) make TWO FRED
    # requests per call, not one. No pacing here previously — caught via
    # live use: the exact same command returned FEWER usable signal
    # readings on a second run than the first (240 -> 220 of 261 dates),
    # consistent with some requests silently getting rate-limited partway
    # through. HONEST CAVEAT: the delay below is a reasonably conservative
    # default based on FRED's generally-documented limits, not a value
    # verified against a live response from this development environment
    # (no network access here) — tune --request-delay up if you still see
    # usable-reading counts drop between otherwise-identical runs, or down
    # if it's unnecessarily slow for your key.
    needs_fred_pacing = _needs_fred_pacing(args.signal)

    for i, d in enumerate(test_dates):
        score = signal_fn(d, args.asset)
        if score is not None:
            signal_scores.append((d, score))
        if needs_fred_pacing and i < len(test_dates) - 1:
            time.sleep(args.request_delay)
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(test_dates)} dates processed")

    print(f"  {len(signal_scores)} of {len(test_dates)} dates had a usable signal reading.")

    result = run_backtest(
        signal_name=args.signal, asset=args.asset, signal_scores=signal_scores,
        price_history_oldest_first=price_history, forward_window_days=args.forward_days,
    )

    print(f"\n=== Backtest Result ===")
    print(f"  Signal:              {result.signal_name}")
    print(f"  Asset:               {result.asset}")
    print(f"  Forward window:      {result.forward_window_days} days")
    print(f"  Sample size:         {result.sample_size} (skipped {result.skipped_dates})")
    print(f"  Correlation:         {result.correlation}")
    print(f"  Significance thresh: {result.significance_threshold}")
    print(f"  Likely significant:  {result.likely_significant}")
    print(f"\n  {result.interpretation()}")


if __name__ == "__main__":
    main()
