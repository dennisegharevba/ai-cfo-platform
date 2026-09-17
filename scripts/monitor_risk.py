"""
Risk monitor CLI — read-only, always. Nothing in this script can place,
modify, or cancel an order (see agents/risk_monitor.py's module
docstring). Connects to Alpaca's PAPER endpoint only, the same as
scripts/demo_execution_engine.py — no live-trading flag exists here
either.

Default: one snapshot, then exit. Pass --loop for continuous monitoring,
which tracks the day's starting equity and the all-time peak equity
ACROSS iterations (both reset/update correctly as time passes) and
re-checks the circuit breaker on each interval. If the circuit breaker
trips and TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are configured, sends a
real alert using the same TelegramAlerter already built and tested
earlier in this project — no new alerting code, reusing what's proven.

Run:
    python scripts/monitor_risk.py
    python scripts/monitor_risk.py --loop --interval-seconds 300
    python scripts/monitor_risk.py --max-daily-loss-pct 3 --max-drawdown-pct 10
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ALPACA_API_KEY, ALPACA_API_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from agents.circuit_breaker import CircuitBreakerConfig
from agents.risk_monitor import take_risk_snapshot


def _print_snapshot(snapshot):
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Equity: ${snapshot.account_equity:,.2f}  "
          f"(paper: {snapshot.is_paper})")
    cb = snapshot.circuit_breaker
    print(f"  Daily P&L: {cb.daily_pnl_pct:+.2f}%   Drawdown from peak: {cb.drawdown_from_peak_pct:+.2f}%")
    if cb.should_halt:
        print("  *** CIRCUIT BREAKER TRIPPED ***")
        for r in cb.reasons:
            print(f"    - {r}")
    else:
        print("  Circuit breaker: OK")
    if snapshot.risk_report is not None:
        print(f"  Portfolio risk level: {snapshot.risk_report.risk_level.value}")
        for e in snapshot.risk_report.evidence:
            print(f"    - {e}")
    else:
        print("  No open positions.")


def _maybe_alert(snapshot):
    if not snapshot.circuit_breaker.should_halt:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  (Circuit breaker tripped, but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID aren't set — no alert sent.)")
        return
    from telegram.telegram_alerter import TelegramAlerter, TelegramError
    message = (
        f"*CIRCUIT BREAKER TRIPPED*\nEquity: ${snapshot.account_equity:,.2f}\n"
        + "\n".join(f"- {r}" for r in snapshot.circuit_breaker.reasons)
    )
    try:
        TelegramAlerter(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID).send_message(message)
        print("  Alert sent via Telegram.")
    except TelegramError as exc:
        print(f"  Alert FAILED to send: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Risk monitor — read-only, paper account only.")
    parser.add_argument("--loop", action="store_true", help="Monitor continuously instead of taking one snapshot")
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--max-daily-loss-pct", type=float, default=5.0)
    parser.add_argument("--max-drawdown-pct", type=float, default=15.0)
    args = parser.parse_args()

    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        print("ALPACA_API_KEY / ALPACA_API_SECRET are not set in .env. Set them and re-run.")
        return

    from brokers.alpaca_connector import AlpacaConnector
    broker = AlpacaConnector(api_key=ALPACA_API_KEY, api_secret=ALPACA_API_SECRET)  # paper — always, this script never passes live_trading_confirmed
    assert broker.is_paper, "SAFETY FAILURE: this script must never connect to a live account."

    config = CircuitBreakerConfig(max_daily_loss_pct=args.max_daily_loss_pct, max_total_drawdown_pct=args.max_drawdown_pct)

    try:
        account = broker.get_account()
    except Exception as exc:
        print(f"Could not connect to Alpaca: {exc}")
        return

    peak_equity = account.equity
    daily_starting_equity = account.equity
    current_day = date.today()

    print(f"=== Risk Monitor (paper) — starting equity ${account.equity:,.2f} ===")
    if args.loop:
        print(f"Looping every {args.interval_seconds}s. Ctrl+C to stop.")

    while True:
        if date.today() != current_day:
            # A new day: reset the daily-loss reference point. The peak
            # equity reference is intentionally NOT reset — it tracks
            # the all-time high regardless of day boundaries.
            current_day = date.today()
            daily_starting_equity = broker.get_account().equity

        snapshot = take_risk_snapshot(
            broker, daily_starting_equity=daily_starting_equity, peak_equity=peak_equity, circuit_breaker_config=config,
        )
        peak_equity = max(peak_equity, snapshot.account_equity)

        _print_snapshot(snapshot)
        _maybe_alert(snapshot)

        if not args.loop:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
