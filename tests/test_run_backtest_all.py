from datetime import date, timedelta
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.run_backtest_all as batch_module


def _flat_price_history(n=400):
    return [(date(2024, 1, 1) + timedelta(days=i), 100.0 + (i % 60) * 0.3) for i in range(n)]


def test_unknown_signal_name_reported_clearly_not_crashed_on(capsys):
    sys.argv = ["run_backtest_all.py", "--asset", "Gold", "--signals", "not_a_real_signal"]
    batch_module.main()
    output = capsys.readouterr().out
    assert "Unknown signal" in output
    assert "not_a_real_signal" in output


def test_missing_fred_key_blocks_fred_signals_but_not_seasonality(capsys):
    with patch.object(batch_module, "FRED_API_KEY", ""):
        sys.argv = ["run_backtest_all.py", "--asset", "Gold", "--signals", "vix"]
        batch_module.main()
    output = capsys.readouterr().out
    assert "FRED_API_KEY is not set" in output


def test_price_history_fetched_exactly_once_regardless_of_signal_count(capsys):
    """The whole point of this script over running scripts/run_backtest.py
    N separate times: ONE price fetch, reused across every signal."""
    with patch.object(batch_module, "_fetch_price_history") as mock_fetch, \
         patch.object(batch_module, "FRED_API_KEY", "FAKE_KEY"), \
         patch.object(batch_module, "SIGNAL_FUNCTIONS", {
             "seasonality": lambda d, asset: 50.0,
             "fake_signal_two": lambda d, asset: -50.0,
         }), \
         patch.object(batch_module, "_needs_fred_pacing", lambda name: False):
        mock_fetch.return_value = _flat_price_history()
        sys.argv = [
            "run_backtest_all.py", "--asset", "Gold", "--signals", "all",
            "--start", "2024-01-01", "--end", "2024-03-01", "--step-days", "20",
        ]
        batch_module.main()

    mock_fetch.assert_called_once()
    output = capsys.readouterr().out
    assert "Reused across all 2 signal(s)" in output


def test_summary_table_sorted_by_absolute_correlation_descending(capsys):
    with patch.object(batch_module, "_fetch_price_history") as mock_fetch, \
         patch.object(batch_module, "FRED_API_KEY", "FAKE_KEY"), \
         patch.object(batch_module, "SIGNAL_FUNCTIONS", {
             "weak_signal": lambda d, asset: 1.0 if d.day % 2 == 0 else -1.0,     # near-zero correlation
             "strong_signal": lambda d, asset: 80.0 if d.month <= 3 else -80.0,   # should correlate more strongly with the trend below
         }), \
         patch.object(batch_module, "_needs_fred_pacing", lambda name: False):
        # A genuine trend: price rises steadily through the test window.
        mock_fetch.return_value = [(date(2024, 1, 1) + timedelta(days=i), 100.0 + i * 0.5) for i in range(400)]
        sys.argv = [
            "run_backtest_all.py", "--asset", "SPY", "--signals", "all",
            "--start", "2024-01-01", "--end", "2024-06-01", "--step-days", "15",
        ]
        batch_module.main()

    output = capsys.readouterr().out
    summary_start = output.index("SUMMARY")
    summary_section = output[summary_start:summary_start + 400]
    # Whichever signal has the larger |correlation| must appear FIRST in the table.
    strong_pos = summary_section.index("strong_signal")
    weak_pos = summary_section.index("weak_signal")
    assert strong_pos < weak_pos


def test_zero_sample_signal_does_not_crash_the_summary(capsys):
    with patch.object(batch_module, "_fetch_price_history") as mock_fetch, \
         patch.object(batch_module, "FRED_API_KEY", "FAKE_KEY"), \
         patch.object(batch_module, "SIGNAL_FUNCTIONS", {"always_none": lambda d, asset: None}), \
         patch.object(batch_module, "_needs_fred_pacing", lambda name: False):
        mock_fetch.return_value = _flat_price_history()
        sys.argv = [
            "run_backtest_all.py", "--asset", "Gold", "--signals", "all",
            "--start", "2024-01-01", "--end", "2024-03-01", "--step-days", "20",
        ]
        batch_module.main()  # must not raise

    output = capsys.readouterr().out
    assert "always_none" in output
    assert "n/a" in output
