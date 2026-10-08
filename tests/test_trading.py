import asyncio
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models import Signal
from app.paper import PaperAccount
from app.trading import calendar, journal, simulate, strategy
from app.trading.brokers import Account, Position
from app.trading.trader import Context, Intent, Trader, check, count_day_trades, plan

MIDDAY = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)  # Wed 11:00 ET


def ctx(**kw):
    base = dict(now=MIDDAY, account=Account(equity=100_000, cash=50_000), positions={}, trades_today=0,
                day_trades_5d=0, bought_today=set(), loss_sales_30d=set(), failed_sources=0, halted=False)
    return Context(**{**base, **kw})


def sig(t, score, price=100.0, conf=0.8):
    return Signal(ticker=t, price=price, change_pct=0, score=score, stance="bullish" if score > 20 else "neutral",
                  confidence=conf, components={"news": 0.5, "insiders": 0.2}, counts={})


@pytest.fixture
def cfg():
    return strategy.Strategy()


def test_calendar():
    assert calendar.is_open(MIDDAY)
    assert not calendar.is_open(datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc))  # Saturday
    assert not calendar.is_open(datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc))  # Thanksgiving
    assert not calendar.is_open(datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc))  # 2pm ET, early close
    assert not calendar.is_open(datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc))  # 9:00 ET, pre-open


def test_strategy_rejects_typos(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("[risk]\nmax_order_usdd = 5\n")
    with pytest.raises(ValueError, match="max_order_usdd"):
        strategy.load(str(p))


def test_entry_and_exit_rules(cfg):
    assert strategy.entry_reasons(cfg, sig("A", 50))
    assert strategy.entry_reasons(cfg, sig("A", 30)) is None
    assert strategy.entry_reasons(cfg, sig("A", 50, conf=0.3)) is None
    cfg.entry.min_components = {"insiders": 0.5}
    assert strategy.entry_reasons(cfg, sig("A", 50)) is None
    assert strategy.exit_reason(cfg, 100, 91, 50, 1).startswith("stop-loss")
    assert strategy.exit_reason(cfg, 100, 116, 50, 1).startswith("take-profit")
    assert strategy.exit_reason(cfg, 100, 101, -5, 1).startswith("score fell")
    assert strategy.exit_reason(cfg, 100, 101, 50, 25).startswith("held")
    assert strategy.exit_reason(cfg, 100, 101, 50, 1) is None
    assert strategy.position_qty(cfg, 100_000, 300) == 6  # capped by max_order_usd $2,000


def test_risk_checks(cfg):
    ok = Intent("A", "buy", 10, 100, 50, ["x"])
    assert check(cfg, ok, ctx()) == []
    assert any("trades/day" in b for b in check(cfg, ok, ctx(trades_today=6)))
    assert any("over max" in b for b in check(cfg, Intent("A", "buy", 30, 100, 50, []), ctx()))
    assert any("daily loss" in b for b in check(cfg, ok, ctx(halted=True)))
    assert any("data sources" in b for b in check(cfg, ok, ctx(failed_sources=2)))
    assert any("wash-sale" in b for b in check(cfg, ok, ctx(loss_sales_30d={"A"})))
    early = datetime(2026, 10, 7, 13, 40, tzinfo=timezone.utc)  # 9:40 ET
    assert any("after open" in b for b in check(cfg, ok, ctx(now=early)))
    full = {t: Position(t, 1, 1) for t in "BCDEF"}
    assert any("positions" in b for b in check(cfg, ok, ctx(positions=full)))
    assert any("spendable cash" in b for b in check(cfg, ok, ctx(account=Account(100_000, 500))))
    # exits ignore entry-only limits...
    sell = Intent("A", "sell", 10, 100, -50, ["stop"], is_exit=True)
    assert check(cfg, sell, ctx(halted=True, failed_sources=5, positions=full)) == []
    big_winner = Intent("A", "sell", 100, 100, 50, ["take-profit"], is_exit=True)  # $10k > $2k order cap
    assert check(cfg, big_winner, ctx()) == []
    # ...but respect the day-trade limit
    assert any("day trade" in b for b in check(cfg, sell, ctx(bought_today={"A"}, day_trades_5d=3)))
    cfg.risk.max_day_trades_per_5d = -1
    assert check(cfg, sell, ctx(bought_today={"A"}, day_trades_5d=3)) == []


def test_count_day_trades():
    fills = [{"ts": "2026-10-07T15:00:00+00:00", "ticker": "A", "side": "buy"},
             {"ts": "2026-10-07T18:00:00+00:00", "ticker": "A", "side": "sell"},
             {"ts": "2026-10-07T15:00:00+00:00", "ticker": "B", "side": "buy"},
             {"ts": "2026-10-08T15:00:00+00:00", "ticker": "B", "side": "sell"}]
    assert count_day_trades(fills) == 1


def test_plan_exits_before_entries(cfg):
    c = ctx(positions={"A": Position("A", 10, 120)})
    intents = plan(cfg, c, {"A": sig("A", 50, price=100), "B": sig("B", 60)}, {"A": 2})
    assert [(i.ticker, i.side) for i in intents] == [("A", "sell"), ("B", "buy")]
    assert intents[0].urgent


@pytest.fixture
def loose(tmp_path, monkeypatch):
    p = tmp_path / "strategy.toml"
    p.write_text("[entry]\nmin_score = -100\nmin_confidence = 0\n[sizing]\nmax_positions = 2\n"
                 "[autopilot]\ncore_pct = 0\ncash_reserve_pct = 0\n")
    monkeypatch.setattr(settings, "strategy_path", str(p))
    for k in ("mode", "broker", "kill_switch", "halted_on"):
        journal.put(k, None)
    journal._db().execute("DELETE FROM decisions")  # trades from other tests would count toward today's limits
    journal._db().execute("DELETE FROM proposals")
    journal.put("kill_switch", False)
    return Trader(PaperAccount(":memory:", starting_cash=100_000))


def test_cycle_off_and_closed(loose):
    journal.put("mode", "off")
    assert asyncio.run(loose.cycle(MIDDAY))["skipped"] == "autotrader is off"
    loose.set_mode("auto", "sim")
    assert asyncio.run(loose.cycle(datetime(2026, 10, 10, 15, tzinfo=timezone.utc)))["skipped"] == "market closed"


def test_approve_mode_flow(loose):
    loose.set_mode("approve", "sim")
    out = asyncio.run(loose.cycle(MIDDAY))
    assert [a["status"] for a in out["actions"]] == ["proposed", "proposed"]  # capped by max_positions
    pending = journal.proposals("pending")
    assert len(pending) >= 2
    asyncio.run(loose.cycle(MIDDAY))  # same ideas aren't proposed twice
    assert len(journal.proposals("pending")) == len(pending)
    with pytest.raises(ValueError, match="market is closed"):
        asyncio.run(loose.approve(pending[0]["proposal_id"], now=datetime(2026, 10, 10, 15, tzinfo=timezone.utc)))
    d = asyncio.run(loose.approve(pending[0]["proposal_id"], now=MIDDAY))
    assert d["status"] == "filled"
    loose.reject(pending[1]["proposal_id"])
    assert loose.ledger.summary({})["positions"]
    loose.set_mode("auto", "sim")  # leaving approve mode cancels what's still waiting
    assert journal.proposals("pending") == []


def test_auto_mode_and_kill_switch(loose):
    loose.set_mode("auto", "sim")
    out = asyncio.run(loose.cycle(MIDDAY))
    assert out["actions"] and all(a["status"] == "filled" for a in out["actions"])
    asyncio.run(loose.kill())
    assert journal.get("mode") == "off"
    loose.set_mode("auto", "sim")
    assert asyncio.run(loose.cycle(MIDDAY))["skipped"] == "kill switch is on"
    loose.reset_kill()


def test_live_auto_needs_explicit_opt_in(loose, monkeypatch):
    monkeypatch.setattr(settings, "allow_live_auto", False)
    with pytest.raises(ValueError, match="ALLOW_LIVE_AUTO"):
        loose.set_mode("auto", "robinhood")
    loose.set_mode("approve", "robinhood")


def test_daily_loss_halts_buys(loose):
    loose.set_mode("auto", "sim")
    today = MIDDAY.astimezone(calendar.ET).date().isoformat()
    journal.put(f"equity_open:sim:{today}", 200_000)  # pretend we started the day at 200k
    out = asyncio.run(loose.cycle(MIDDAY))
    assert all(a["status"] == "blocked" for a in out["actions"])
    assert journal.get("halted_on") == today


def test_simulate_rules_vs_benchmark(cfg):
    from app.models import PriceInfo
    dates = [f"2026-01-{d:02d}" for d in range(1, 31)]
    up = PriceInfo(ticker="UP", price=0, prev_close=0, closes=[100 * 1.01 ** i for i in range(30)], dates=dates)
    spy = PriceInfo(ticker="SPY", price=0, prev_close=0, closes=[100] * 30, dates=dates)
    r = simulate.run({"UP": {d: 80 for d in dates}}, {"UP": up}, cfg, benchmark=spy)
    assert r["trades"] >= 1 and r["total_return_pct"] > 0 and r["beats_benchmark"]
    assert r["max_drawdown_pct"] <= 0
