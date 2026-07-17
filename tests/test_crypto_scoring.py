from agents.crypto_scoring import funding_rate_bias_score, funding_rate_extremity_flag


def test_positive_funding_gives_positive_score():
    assert funding_rate_bias_score(0.0003) > 0


def test_negative_funding_gives_negative_score():
    assert funding_rate_bias_score(-0.0003) < 0


def test_zero_funding_gives_zero_score():
    assert funding_rate_bias_score(0.0) == 0.0


def test_score_clamped_at_100():
    assert funding_rate_bias_score(0.01) == 100.0
    assert funding_rate_bias_score(-0.01) == -100.0


def test_extreme_positive_funding_flagged_crowded_long():
    assert funding_rate_extremity_flag(0.0015) == "crowded_long"


def test_extreme_negative_funding_flagged_crowded_short():
    assert funding_rate_extremity_flag(-0.0015) == "crowded_short"


def test_normal_funding_not_flagged():
    assert funding_rate_extremity_flag(0.0002) is None
