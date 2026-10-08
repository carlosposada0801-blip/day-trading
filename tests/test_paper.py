import pytest

from app.paper import PaperAccount, TradeError


@pytest.fixture
def acct():
    return PaperAccount(":memory:", starting_cash=10_000)


def test_buy_sell_pnl(acct):
    acct.order("AAPL", "buy", 10, 100, {})
    acct.order("AAPL", "sell", 4, 120, {"AAPL": 100})
    s = acct.summary({"AAPL": 110})
    assert s["realized_pnl"] == 80
    assert s["positions"][0]["qty"] == 6
    assert s["positions"][0]["unrealized"] == 60
    assert s["cash"] == 10_000 - 1000 + 480
    assert s["total_pnl"] == 140


def test_no_shorting(acct):
    with pytest.raises(TradeError, match="no shorting"):
        acct.order("AAPL", "sell", 1, 100, {})


def test_insufficient_cash(acct):
    with pytest.raises(TradeError, match="insufficient cash"):
        acct.order("AAPL", "buy", 1000, 100, {})


def test_position_size_limit(acct):
    # default limit is 20% of equity -> $2,000 on a $10k account
    acct.order("AAPL", "buy", 19, 100, {})
    with pytest.raises(TradeError, match="risk limit"):
        acct.order("AAPL", "buy", 2, 100, {"AAPL": 100})
