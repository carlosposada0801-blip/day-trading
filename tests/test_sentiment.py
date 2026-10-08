from app import sentiment


def test_positive_and_negative_headlines():
    assert sentiment.score("Apple beats estimates as iPhone sales surge") > 0.5
    assert sentiment.score("Tesla shares plunge after analyst downgrade") < -0.5
    assert sentiment.score("Microsoft to hold annual meeting Tuesday") == 0


def test_negation_flips():
    assert sentiment.score("this is not bullish") < 0


def test_social_slang_and_emoji():
    assert sentiment.score("$GME to the moon 🚀🚀") > 0.5
    assert sentiment.score("bagholding this one 💀📉") < -0.5


def test_extract_tickers():
    text = "$nvda and AMD calls, YOLO into TSLA. CEO said DD is solid"
    assert sentiment.extract_tickers(text, {"AMD", "TSLA"}) == {"NVDA", "AMD", "TSLA"}
    # bare caps words only count when known
    assert sentiment.extract_tickers("IBM is up", set()) == set()
