from agents.sentiment_scoring import news_sentiment_score


def test_bullish_headlines_give_positive_score():
    headlines = [
        "Stocks rally as earnings beat expectations",
        "Market hits record high on strong jobs data",
    ]
    score = news_sentiment_score(headlines)
    assert score is not None
    assert score > 0


def test_bearish_headlines_give_negative_score():
    headlines = [
        "Markets plunge on recession fears",
        "Tech selloff deepens as layoffs mount",
    ]
    score = news_sentiment_score(headlines)
    assert score is not None
    assert score < 0


def test_neutral_headlines_give_near_zero_score():
    headlines = [
        "Fed holds rates steady",
        "Quarterly report released today",
    ]
    score = news_sentiment_score(headlines)
    assert score == 0.0


def test_empty_headlines_returns_none():
    assert news_sentiment_score([]) is None


def test_mixed_headlines_net_out():
    headlines = ["Stocks rally", "Stocks crash", "Markets flat"]
    score = news_sentiment_score(headlines)
    assert score == 0.0  # one bullish, one bearish, one neutral -> nets to zero


def test_case_insensitive_matching():
    headlines = ["STOCKS RALLY TO RECORD HIGH"]
    score = news_sentiment_score(headlines)
    assert score is not None
    assert score > 0
