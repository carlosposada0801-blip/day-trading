from datetime import datetime, timezone

from app import signals
from app.models import Article, FundMove, PriceInfo, SocialPost

NOW = datetime.now(timezone.utc)


def art(s):
    return Article(ticker="X", title="t", url="#", source="s", published=NOW, sentiment=s)


def post(s, score=0):
    return SocialPost(ticker="X", text="t", url="#", platform="demo", score=score, created=NOW, sentiment=s)


def test_all_bullish_inputs_give_bullish_signal():
    price = PriceInfo(ticker="X", price=110, prev_close=108, closes=[100, 101, 102, 104, 106, 108, 110])
    moves = [FundMove(fund="F", ticker="X", issuer="X", shares=200, prev_shares=100, value_usd=1, period="p")]
    s = signals.build("X", price, [art(0.8)] * 5, [post(0.7)] * 5, moves)
    assert s.stance == "bullish" and s.score > 50
    assert s.confidence > 0.5


def test_missing_sources_are_excluded_not_zeroed():
    s = signals.build("X", None, [art(-0.9)], [], [])
    assert s.components["social"] is None and s.components["momentum"] is None
    assert s.score < -80  # only news counted, at full weight
    assert s.confidence < 0.4  # but little data backs it


def test_no_data_is_neutral():
    s = signals.build("X", None, [], [], [])
    assert s.score == 0 and s.stance == "neutral" and s.confidence == 0


def test_upvotes_weight_social():
    assert signals.social_component([post(1.0, score=5000), post(-1.0, score=0)]) > 0.5


def test_fund_exit_is_bearish():
    m = FundMove(fund="F", ticker="X", issuer="X", shares=0, prev_shares=100, value_usd=0, period="p")
    assert signals.funds_component([m]) < -0.9


def test_insider_buying_is_bullish_and_selling_weighs_less():
    from datetime import date
    from app.models import InsiderTrade
    today = date.today().isoformat()
    buy = InsiderTrade(ticker="X", insider="a", title="CEO", code="P", shares=10_000, price=50, date=today)
    sell = InsiderTrade(ticker="X", insider="b", title="CFO", code="S", shares=10_000, price=50, date=today)
    assert signals.insiders_component([buy]) > 0.6
    assert signals.insiders_component([buy, sell]) > 0  # same $ sold doesn't cancel a buy
    old = buy.model_copy(update={"date": "2020-01-01"})
    assert signals.insiders_component([old]) is None


def test_congress_component():
    from datetime import date
    from app.models import CongressTrade
    t = CongressTrade(ticker="X", member="m", chamber="House", side="sell", amount_low=100_001,
                      amount_high=250_000, traded=date.today().isoformat(), disclosed="")
    assert signals.congress_component([t]) < -0.9
