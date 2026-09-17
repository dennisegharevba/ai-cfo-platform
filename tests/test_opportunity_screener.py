from datetime import date, timedelta

from agents.opportunity_screener import (
    ScreenedOpportunity, screen_asset, rank_opportunities, rank_opportunities_by_class, _price_history_to_technical_input,
)


def _uptrend(n=120, base=None):
    base = base or date(2024, 1, 1)
    return [(base + timedelta(days=i), 100.0 + i * 0.8) for i in range(n)]


def _downtrend(n=120, base=None):
    base = base or date(2024, 1, 1)
    return [(base + timedelta(days=i), 300.0 - i * 0.8) for i in range(n)]


# --- _price_history_to_technical_input ---

def test_conversion_reverses_order_to_newest_first():
    history = [(date(2024, 1, 1), 100.0), (date(2024, 1, 2), 101.0), (date(2024, 1, 3), 102.0)]
    converted = _price_history_to_technical_input(history)
    assert converted[0]["close"] == 102.0  # newest first
    assert converted[-1]["close"] == 100.0  # oldest last


def test_conversion_produces_the_expected_dict_shape():
    history = [(date(2024, 1, 1), 100.0)]
    converted = _price_history_to_technical_input(history)
    assert converted[0]["close"] == 100.0
    assert converted[0]["date"] == "2024-01-01"


# --- screen_asset ---

def test_screen_asset_returns_none_for_insufficient_history():
    short_history = [(date(2024, 1, 1), 100.0), (date(2024, 1, 2), 101.0)]
    assert screen_asset("Test", "X", "equity", short_history) is None


def test_screen_asset_identifies_a_genuine_uptrend_as_long():
    opp = screen_asset("Gold", "GC=F", "commodity", _uptrend())
    assert opp is not None
    assert opp.direction == "long"
    assert opp.bias_score > 0
    assert opp.label == "Gold"
    assert opp.ticker == "GC=F"
    assert opp.asset_class == "commodity"


def test_screen_asset_identifies_a_genuine_downtrend_as_short():
    opp = screen_asset("Test", "X", "equity", _downtrend())
    assert opp is not None
    assert opp.direction == "short"
    assert opp.bias_score < 0


def test_conviction_score_computed_correctly():
    opp = screen_asset("Gold", "GC=F", "commodity", _uptrend())
    expected = round(abs(opp.bias_score) * (opp.confidence / 100.0), 2)
    assert opp.conviction_score == expected


def test_screen_asset_without_volume_is_unaffected_backward_compatible():
    """The default (volumes_oldest_first=None) must produce an identical
    result to before volume support was added — proven by comparing
    against the exact pre-existing hand-computed formula."""
    opp = screen_asset("Gold", "GC=F", "commodity", _uptrend())
    expected = round(abs(opp.bias_score) * (opp.confidence / 100.0), 2)
    assert opp.conviction_score == expected


def test_screen_asset_boosts_conviction_for_elevated_volume():
    history = _uptrend()
    elevated_volumes = [1_000_000.0] * 45 + [2_000_000.0] * 5  # oldest first: recent days elevated
    without_volume = screen_asset("Gold", "GC=F", "commodity", history)
    with_volume = screen_asset("Gold", "GC=F", "commodity", history, volumes_oldest_first=elevated_volumes)
    assert with_volume.conviction_score > without_volume.conviction_score


def test_screen_asset_reduces_conviction_for_below_average_volume():
    history = _uptrend()
    low_volumes = [1_000_000.0] * 45 + [400_000.0] * 5  # oldest first: recent days below average
    without_volume = screen_asset("Gold", "GC=F", "commodity", history)
    with_volume = screen_asset("Gold", "GC=F", "commodity", history, volumes_oldest_first=low_volumes)
    assert with_volume.conviction_score < without_volume.conviction_score


def test_screen_asset_no_penalty_for_unusable_volume_data():
    """THE core fairness test at the full screen_asset() level: an
    instrument with all-zero volume (common for FX pairs via Yahoo) must
    score IDENTICALLY to not passing volume data at all — never worse,
    which would unfairly penalize an entire asset class for a data
    source's own coverage gap."""
    history = _uptrend()
    zero_volumes = [0.0] * 120
    without_volume = screen_asset("EUR/USD", "EURUSD=X", "fx", history)
    with_zero_volume = screen_asset("EUR/USD", "EURUSD=X", "fx", history, volumes_oldest_first=zero_volumes)
    assert with_zero_volume.conviction_score == without_volume.conviction_score


def test_annualized_vol_pct_is_populated_and_positive():
    """The diagnostic field added after a real live run left an open
    question about whether equities' continued dominance in real results
    reflects genuine market structure or a remaining calibration issue —
    exposing the actual volatility figure used lets that be checked
    directly against real output, rather than trusted blindly."""
    opp = screen_asset("Gold", "GC=F", "commodity", _uptrend())
    assert opp.annualized_vol_pct is not None
    assert opp.annualized_vol_pct > 0


def test_screen_asset_fairly_ranks_a_calm_asset_above_a_volatile_one_with_the_same_underlying_trend():
    """
    THE core regression test for the real bug found via live testing: a
    real screener run across equities/commodities/FX/crypto came back
    essentially 100% volatile growth stocks — not because those assets
    genuinely had the best opportunities, but because comparing raw price
    moves across wildly different volatility profiles structurally
    favored whichever class happened to be more volatile. Reproduces that
    exact scenario directly: two assets with the IDENTICAL underlying
    trend (same daily drift), one with small daily noise (like a major FX
    pair), one with large daily noise (like a growth stock). The calm one
    must now score meaningfully HIGHER, not lower or the same — the
    opposite of what a flat, unnormalized comparison would have produced.
    """
    import random
    random.seed(42)
    base = date(2024, 1, 1)
    calm_asset = [(base + timedelta(days=i), 100.0 + i * 0.15 + random.gauss(0, 0.3)) for i in range(150)]
    volatile_asset = [(base + timedelta(days=i), 100.0 + i * 0.15 + random.gauss(0, 3.0)) for i in range(150)]

    calm_result = screen_asset("CalmFX", "CALM", "fx", calm_asset)
    volatile_result = screen_asset("VolatileStock", "VOL", "equity", volatile_asset)

    assert calm_result is not None and volatile_result is not None
    assert calm_result.conviction_score > volatile_result.conviction_score


# --- rank_opportunities ---

def test_rank_filters_by_minimum_confidence():
    opps = [
        ScreenedOpportunity("A", "A", "equity", 50.0, 80.0, "long", 40.0, 20.0),
        ScreenedOpportunity("B", "B", "equity", 30.0, 20.0, "long", 6.0, 20.0),
    ]
    ranked = rank_opportunities(opps, min_confidence=40.0)
    assert [o.label for o in ranked] == ["A"]


def test_rank_sorts_by_conviction_score_descending():
    opps = [
        ScreenedOpportunity("A", "A", "equity", 50.0, 80.0, "long", 40.0, 20.0),
        ScreenedOpportunity("B", "B", "equity", 90.0, 90.0, "long", 81.0, 20.0),
        ScreenedOpportunity("D", "D", "equity", 70.0, 70.0, "short", 49.0, 20.0),
    ]
    ranked = rank_opportunities(opps, min_confidence=0.0)
    assert [o.label for o in ranked] == ["B", "D", "A"]


def test_rank_respects_top_n():
    opps = [
        ScreenedOpportunity(str(i), str(i), "equity", 50.0, 80.0, "long", float(i), 20.0)
        for i in range(20)
    ]
    ranked = rank_opportunities(opps, min_confidence=0.0, top_n=5)
    assert len(ranked) == 5


def test_rank_empty_input_returns_empty():
    assert rank_opportunities([], min_confidence=40.0, top_n=10) == []


def test_rank_ties_keep_original_scan_order_not_shuffled():
    opps = [
        ScreenedOpportunity("First", "F", "equity", 50.0, 80.0, "long", 40.0, 20.0),
        ScreenedOpportunity("Second", "S", "equity", 50.0, 80.0, "long", 40.0, 20.0),
    ]
    ranked = rank_opportunities(opps, min_confidence=0.0)
    assert [o.label for o in ranked] == ["First", "Second"]


# --- rank_opportunities_by_class ---

def test_rank_by_class_guarantees_representation_across_every_class():
    """THE core regression test for the real gap found via live testing:
    fixing the cross-asset scoring bias made the ranking fair, but a
    global top-N over a fair ranking can still legitimately come back
    from one class entirely, if that class simply has more/stronger
    genuinely-trending assets right now. Per-class ranking must guarantee
    every class with usable data appears in the result."""
    opps = [
        ScreenedOpportunity("Gold", "GC=F", "commodity", 20.0, 80.0, "long", 16.0, 15.0),
        ScreenedOpportunity("EUR/USD", "EURUSD=X", "fx", 15.0, 80.0, "long", 12.0, 8.0),
        # Three equities, all with much higher conviction than the commodity/FX above —
        # exactly the real-world scenario that motivated this function.
        ScreenedOpportunity("MSFT", "MSFT", "equity", 90.0, 90.0, "long", 81.0, 27.0),
        ScreenedOpportunity("IBM", "IBM", "equity", 85.0, 90.0, "short", 76.5, 28.0),
        ScreenedOpportunity("GLW", "GLW", "equity", 95.0, 90.0, "short", 85.5, 36.0),
    ]
    ranked = rank_opportunities_by_class(opps, min_confidence=0.0, top_n_per_class=2)
    represented_classes = {o.asset_class for o in ranked}
    assert represented_classes == {"commodity", "fx", "equity"}


def test_rank_by_class_respects_top_n_within_each_class_independently():
    opps = [
        ScreenedOpportunity("MSFT", "MSFT", "equity", 90.0, 90.0, "long", 81.0, 27.0),
        ScreenedOpportunity("IBM", "IBM", "equity", 85.0, 90.0, "short", 76.5, 28.0),
        ScreenedOpportunity("GLW", "GLW", "equity", 95.0, 90.0, "short", 85.5, 36.0),
    ]
    ranked = rank_opportunities_by_class(opps, min_confidence=0.0, top_n_per_class=2)
    equity_labels = [o.label for o in ranked if o.asset_class == "equity"]
    assert len(equity_labels) == 2
    assert "IBM" not in equity_labels  # the weakest of the 3, correctly dropped
    assert "GLW" in equity_labels and "MSFT" in equity_labels  # the top 2 by conviction


def test_rank_by_class_still_applies_min_confidence_within_each_class():
    opps = [
        ScreenedOpportunity("Gold", "GC=F", "commodity", 90.0, 90.0, "long", 81.0, 15.0),
        ScreenedOpportunity("Silver", "SI=F", "commodity", 30.0, 20.0, "long", 6.0, 20.0),  # confidence too low
    ]
    ranked = rank_opportunities_by_class(opps, min_confidence=40.0, top_n_per_class=5)
    assert [o.label for o in ranked] == ["Gold"]


def test_rank_by_class_empty_input_returns_empty():
    assert rank_opportunities_by_class([], min_confidence=40.0, top_n_per_class=3) == []


def test_rank_by_class_output_grouped_in_first_seen_class_order():
    opps = [
        ScreenedOpportunity("EUR/USD", "EURUSD=X", "fx", 50.0, 80.0, "long", 40.0, 8.0),
        ScreenedOpportunity("Gold", "GC=F", "commodity", 50.0, 80.0, "long", 40.0, 15.0),
        ScreenedOpportunity("GBP/USD", "GBPUSD=X", "fx", 40.0, 80.0, "long", 32.0, 8.0),
    ]
    ranked = rank_opportunities_by_class(opps, min_confidence=0.0, top_n_per_class=5)
    # fx appeared first in the input -> fx entries should come first in the output, grouped together
    assert [o.asset_class for o in ranked] == ["fx", "fx", "commodity"]
