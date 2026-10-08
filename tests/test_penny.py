import asyncio
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models import PriceInfo, Signal
from app.paper import PaperAccount
from app.sources import demo, prices
from app.trading import journal, penny, strategy
from app.trading.brokers import Account, Position
from app.trading.trader import Context, Trader, check, plan

MIDDAY = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


def cfg_on():
    c = strategy.Strategy()
    c.penny.enabled = True
    return c


def pi(price, vol=2_000_000, exchange="NasdaqCM", closes=None):
    closes = closes or [price] * 22
    return PriceInfo(ticker="X", price=price, prev_close=price, closes=closes, volumes=[vol] * len(closes),
                     exchange=exchange)


def sig(t="X", score=60, social=0.1, news=0.3, n_social=3, price=2.0):
    return Signal(ticker=t, price=price, change_pct=0, score=score, stance="bullish", confidence=0.7,
                  components={"social": social, "news": news}, counts={"social": n_social})


def test_eligibility():
    c = cfg_on()
    assert penny.eligibility(c, pi(2.0)) == []
    assert any("over-the-counter" in r for r in penny.eligibility(c, pi(2.0, exchange="PNK")))
    assert any("under $0.50" in r for r in penny.eligibility(c, pi(0.3)))
    assert any("not a penny" in r for r in penny.eligibility(c, pi(7.0)))
    assert any("hard to sell" in r for r in penny.eligibility(c, pi(2.0, vol=10_000)))  # $20k/day
    assert penny.eligibility(c, None) == ["no price data"]


def test_pump_guard():
    c = cfg_on()
    run_up = [1.0] * 16 + [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]  # +100% over the last 5 days
    hyped = pi(2.0, closes=run_up)
    assert penny.pump_flags(c, hyped, sig(social=0.6, news=None))  # hype, no news: pump
    assert penny.pump_flags(c, hyped, sig(social=0.6, news=0.5)) == []  # real news behind it
    assert penny.pump_flags(c, pi(2.0), sig(social=0.9, news=None)) == []  # no run-up
    spiky = hyped.model_copy(update={"volumes": [1e6] * 17 + [9e6] * 5})
    assert any("volume" in f for f in penny.pump_flags(c, spiky, sig(social=0.0, news=0.5)))
    c.penny.pump_guard = False
    assert penny.pump_flags(c, hyped, sig(social=0.6, news=None)) == []


def test_demo_scan_blocks_each_trap():
    from app import cache
    cache.clear()
    rows = {r["ticker"]: r for r in asyncio.run(penny.scan(cfg_on()))}
    assert rows["PUMP"]["pump"] and not rows["PUMP"]["eligible"]
    assert any("over-the-counter" in b for b in rows["OTCX"]["blocks"])
    assert any("hard to sell" in b for b in rows["PNYB"]["blocks"])


def ctx(**kw):
    base = dict(now=MIDDAY, account=Account(equity=1_000, cash=1_000), positions={}, trades_today=0,
                day_trades_5d=0, bought_today=set(), loss_sales_30d=set(), failed_sources=0, halted=False,
                spendable=950)
    return Context(**{**base, **kw})


def row(t, price=2.0, eligible=True, score=70):
    return {"ticker": t, "price": price, "exchange": "NasdaqCM", "dollar_volume": 5e6,
            "signal": sig(t, score, price=price), "blocks": [] if eligible else ["nope"], "pump": False,
            "eligible": eligible}


def test_plan_penny_sleeve_budget_and_count():
    c = cfg_on()  # 10%? default budget 15% of $1,000 = $150, 2 positions of $75
    c.autopilot.core_pct = 0
    rows = [row("AAA"), row("BBB", eligible=False), row("CCC"), row("DDD")]
    intents = [i for i in plan(c, ctx(), {}, {}, rows) if i.is_penny]
    assert [i.ticker for i in intents] == ["AAA", "CCC"]  # max 2, ineligible skipped
    assert all(abs(i.qty * i.price - 75) < 0.01 for i in intents)
    assert all(i.reasons[0].startswith("penny") for i in intents)


def test_penny_priced_stocks_skip_regular_buys():
    c = cfg_on()
    c.entry.min_score = -100
    c.entry.min_confidence = 0
    c.autopilot.core_pct = 0
    intents = plan(c, ctx(), {"CHEAP": sig("CHEAP", 90, price=1.5), "BIG": sig("BIG", 50, price=120)}, {}, [])
    assert [i.ticker for i in intents] == ["BIG"]


def test_penny_holdings_use_penny_exit_rules():
    c = cfg_on()
    c.autopilot.core_pct = 0
    pos = {"AAA": Position("AAA", 10, 2.0), "BIG": Position("BIG", 1, 100)}
    sigs = {"AAA": sig("AAA", 60, price=1.80), "BIG": sig("BIG", 60, price=90)}  # both down 10%
    intents = plan(c, ctx(positions=pos, penny_held={"AAA"}), sigs, {}, [])
    sells = {i.ticker for i in intents if i.side == "sell"}
    assert sells == {"BIG"}  # -10% trips the regular 8% stop but not the penny 15% stop
    sigs["AAA"] = sig("AAA", 60, price=1.60)  # -20%
    sells = {i.ticker: i for i in plan(c, ctx(positions=pos, penny_held={"AAA"}), sigs, {}, []) if i.side == "sell"}
    assert sells["AAA"].is_penny and "penny stop-loss" in sells["AAA"].reasons[0]


def test_min_order_size():
    c = strategy.Strategy()
    from app.trading.trader import Intent
    tiny = Intent("X", "buy", 1, 3.0, 50, ["x"])
    assert any("minimum" in b for b in check(c, tiny, ctx()))
    tiny_sell = Intent("X", "sell", 1, 3.0, 50, ["x"], is_exit=True)
    assert not any("minimum" in b for b in check(c, tiny_sell, ctx()))  # small exits always allowed


def test_parse_chart_volume_and_exchange():
    data = {"chart": {"result": [{"meta": {"exchangeName": "PNK"}, "timestamp": [1790000000, 1790086400],
                                  "indicators": {"quote": [{"close": [0.5, 0.6], "volume": [1000, None]}]}}]}}
    p = prices.parse_chart(data, "X")
    assert p.volumes == [1000.0, 0.0] and p.is_otc and p.avg_dollar_volume() == 250.0


@pytest.fixture
def small(tmp_path, monkeypatch):
    p = tmp_path / "strategy.toml"
    p.write_text("[penny]\nenabled = true\nwatchlist = [\"PNYA\"]\nmin_score = -100\nmin_confidence = 0\n")
    monkeypatch.setattr(settings, "strategy_path", str(p))
    for k in ("net_deposits", "reserved", "set_aside_total", "last_cash", "last_ts", "last_equity", "last_deposit_ts"):
        journal.put(f"ap:sim:{k}", None)
    journal.put("kill_switch", False)
    journal.put("halted_on", None)
    journal.put(penny.HELD_KEY, [])
    journal._db().execute("DELETE FROM decisions")
    journal._db().execute("DELETE FROM trade_state WHERE key LIKE 'pnl_open:%'")
    journal._db().execute("DELETE FROM proposals")
    t = Trader(PaperAccount(":memory:", starting_cash=100))
    t.set_mode("auto", "sim")
    return t


def test_hundred_dollar_paycheck_account(small):
    from app import cache
    cache.clear()
    out = asyncio.run(small.cycle(MIDDAY))
    filled = [a for a in out["actions"] if a["status"] == "filled"]
    held = {p["ticker"]: p for p in small.ledger.summary({})["positions"]}
    assert "VOO" in held and 0 < held["VOO"]["qty"] < 1  # a fraction of a $525 share
    assert held["VOO"]["value"] == pytest.approx(60, abs=1)
    assert "PNYA" in held and "PNYA" in penny.held()  # penny bought through its sleeve
    assert held["PNYA"]["value"] <= 15.01  # 15% budget
    assert "PUMP" not in held and "OTCX" not in held
    assert all(d["qty"] * (d["fill_price"] or d["price"]) >= 5 - 0.01
               for d in journal.decisions() if d["status"] == "filled" and d["side"] == "buy")
    assert filled
    # next paycheck
    small.ledger.transfer(100)
    asyncio.run(small.cycle(MIDDAY))
    assert journal.get("ap:sim:net_deposits") == 200
    assert small.ledger.summary({})["positions"][0]["qty"] > 0
