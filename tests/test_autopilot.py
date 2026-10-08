import asyncio
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.paper import PaperAccount
from app.trading import autopilot, journal, strategy
from app.trading.trader import Trader

MIDDAY = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)  # Wed 11:00 ET
NOW = MIDDAY.isoformat()


@pytest.fixture(autouse=True)
def clean():
    for k in ("net_deposits", "reserved", "set_aside_total", "last_cash", "last_ts", "last_equity"):
        for b in ("t", "sim"):
            journal.put(f"ap:{b}:{k}", None)
    journal.put("ap:summary_week", None)


def test_funding_detects_deposits_and_withdrawals():
    f = autopilot.update_funding("t", 10_000, 10_000, [], NOW)
    assert f.net_deposits == 10_000 and f.events == [("start", 10_000)]
    # our own $3,000 buy explains the cash drop: not a withdrawal
    buy = [{"side": "buy", "qty": 10, "fill_price": 300, "limit_price": None, "price": 300}]
    f = autopilot.update_funding("t", 10_000, 7_000, buy, NOW)
    assert f.events == [] and f.net_deposits == 10_000
    f = autopilot.update_funding("t", 12_000, 9_000, [], NOW)
    assert f.events == [("deposit", 2_000)] and f.net_deposits == 12_000
    f = autopilot.update_funding("t", 11_500, 8_500, [], NOW)
    assert f.events == [("withdrawal", 500)] and f.net_deposits == 11_500
    f = autopilot.update_funding("t", 11_510, 8_510, [], NOW)  # $10 of interest: within tolerance
    assert f.events == []
    # an unfilled $1,000 buy expires: cash comes back but equity doesn't move -> not a deposit
    f = autopilot.update_funding("t", 11_515, 9_510, [], NOW)
    assert f.events == [] and f.net_deposits == 11_500


def test_profit_pull_high_water():
    cfg = strategy.Strategy()  # trigger 10%, share 50%
    autopilot.update_funding("t", 10_000, 10_000, [], NOW)
    f = autopilot.load("t")
    assert autopilot.maybe_pull(cfg, f, 10_500, "t", 10_500, NOW) == 0  # only +5%
    assert autopilot.maybe_pull(cfg, f, 12_000, "t", 12_000, NOW) == 1_000  # +20% -> half of $2,000
    assert autopilot.maybe_pull(cfg, f, 12_000, "t", 12_000, NOW) == 0  # already set aside
    assert autopilot.maybe_pull(cfg, f, 11_500, "t", 11_500, NOW) == 0  # profit fell: nothing new
    assert autopilot.maybe_pull(cfg, f, 13_000, "t", 13_000, NOW) == 500  # new high: half of the extra
    # withdrawing the set-aside cash clears the reserve but doesn't re-trigger a pull
    f = autopilot.update_funding("t", 11_500, 0, [], NOW, known_net_deposits=8_500)
    assert f.reserved == 0 and f.set_aside_total == 1_500
    assert autopilot.maybe_pull(cfg, f, 11_500, "t", 0, NOW) == 0
    assert autopilot.release("t") == 0


def test_core_order():
    cfg = strategy.Strategy()  # 60% core, band 5%, $5k steps
    assert autopilot.core_order(cfg, 10_000, 0, 9_000, 0, 500) == ("buy", 10, "invest in VOO: core 0% of target 60%")
    assert autopilot.core_order(cfg, 10_000, 0, 9_000, 12, 500) is None  # 60% exactly
    assert autopilot.core_order(cfg, 10_000, 0, 9_000, 11, 500) is None  # 55%: inside the band
    side, qty, _ = autopilot.core_order(cfg, 10_000, 0, 9_000, 20, 500)  # 100%: trim
    assert (side, qty) == ("sell", 8)
    assert autopilot.core_order(cfg, 100_000, 0, 90_000, 0, 500)[1] == 10  # capped at $5,000 per step
    assert autopilot.core_order(cfg, 10_000, 0, 200, 0, 500) is None  # not enough spendable cash
    cfg.autopilot.core_pct = 0
    assert autopilot.core_order(cfg, 10_000, 0, 9_000, 0, 500) is None


def test_spendable_and_satellite_room():
    cfg = strategy.Strategy()
    assert autopilot.spendable(cfg, 10_000, 4_000, 1_000) == 2_500  # minus $1k set aside and 5% reserve
    assert autopilot.satellite_room(cfg, 10_000, 0, 1_000) == 2_500  # 35% budget minus $1k held


def test_weekly_summary_due():
    fri_after = datetime(2026, 10, 9, 20, 30, tzinfo=timezone.utc)  # 4:30pm ET Friday
    assert autopilot.weekly_summary_due(fri_after) == "2026-W41"
    assert autopilot.weekly_summary_due(datetime(2026, 10, 9, 19, 0, tzinfo=timezone.utc)) is None  # 3pm
    journal.put("ap:summary_week", "2026-W41")
    assert autopilot.weekly_summary_due(fri_after) is None


@pytest.fixture
def trader(tmp_path, monkeypatch):
    p = tmp_path / "strategy.toml"
    p.write_text("[entry]\nmin_score = -100\nmin_confidence = 0\n")  # default autopilot: 60% VOO
    monkeypatch.setattr(settings, "strategy_path", str(p))
    journal.put("kill_switch", False)
    journal.put("halted_on", None)
    journal._db().execute("DELETE FROM decisions")
    journal._db().execute("DELETE FROM proposals")
    t = Trader(PaperAccount(":memory:", starting_cash=20_000))
    t.set_mode("auto", "sim")
    return t


def test_autopilot_invests_deposit_into_core_and_satellites(trader):
    out = asyncio.run(trader.cycle(MIDDAY))
    filled = {(a["ticker"], a["side"]) for a in out["actions"] if a["status"] == "filled"}
    assert ("VOO", "buy") in filled and len(filled) >= 2
    held = {p["ticker"]: p["value"] for p in trader.ledger.summary({})["positions"]}
    sats = sum(v for t, v in held.items() if t != "VOO")
    assert sats <= 20_000 * 0.35 + 1  # satellites stay inside their budget
    # a new deposit is noticed and put to work
    trader.ledger.transfer(10_000)
    out = asyncio.run(trader.cycle(MIDDAY))
    assert journal.get("ap:sim:net_deposits") == 30_000
    assert any(a["ticker"] == "VOO" and a["side"] == "buy" for a in out["actions"])


def test_autopilot_raises_cash_for_profit(trader, monkeypatch):
    from app import cache
    from app.sources import demo
    asyncio.run(trader.cycle(MIDDAY))
    # the market rallies 40%: the account is well past the 10% profit trigger
    real = demo.price

    def rallied(ticker, days=22):
        p = real(ticker, days)
        return p.model_copy(update={"price": round(p.price * 1.4, 2), "closes": [c * 1.4 for c in p.closes]})

    monkeypatch.setattr(demo, "price", rallied)
    cache.clear()
    out = asyncio.run(trader.cycle(MIDDAY))
    reserved = journal.get("ap:sim:reserved")
    assert reserved > 2_000  # half of a several-thousand-dollar gain
    sells = [a for a in out["actions"] if a["side"] == "sell" and a["status"] == "filled"]
    assert sells, "should sell some holdings to raise the cash it set aside"
    s = trader.ledger.summary({})
    assert s["cash"] >= reserved - 1
    # set-aside cash is never reinvested on later cycles
    asyncio.run(trader.cycle(MIDDAY))
    assert trader.ledger.summary({})["cash"] >= reserved - 1
