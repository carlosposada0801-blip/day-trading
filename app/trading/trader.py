"""The autotrader: each cycle checks exits, then entries, runs every risk check, and then
either does nothing (off), asks you (approve), or places the order (auto)."""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app import data, engine
from app.config import settings
from app.notify import push
from app.trading import calendar, journal, strategy
from app.trading.brokers import Account, Broker, BrokerError, Position, SimBroker

log = logging.getLogger(__name__)
MODES = ("off", "approve", "auto")


@dataclass
class Intent:
    ticker: str
    side: str
    qty: float
    price: float
    score: float | None
    reasons: list[str]
    is_exit: bool = False
    urgent: bool = False  # stop-loss
    avg_cost: float | None = None  # for sells: lets us tag loss sales for wash-sale tracking


@dataclass
class Context:
    now: datetime
    account: Account
    positions: dict[str, Position]
    trades_today: int
    day_trades_5d: int
    bought_today: set[str]
    loss_sales_30d: set[str]
    failed_sources: int
    halted: bool
    new_positions: int = 0
    notes: list[str] = field(default_factory=list)
    ignore_hours: bool = False  # demo-mode "run now" outside market hours


def state() -> dict:
    return {
        "mode": journal.get("mode", "off"),
        "broker": journal.get("broker", "sim"),
        "kill_switch": journal.get("kill_switch", False),
        "halted_on": journal.get("halted_on"),
        "last_cycle": journal.get("last_cycle"),
        "last_summary": journal.get("last_summary"),
    }


def _et_day_start(now: datetime) -> datetime:
    d = now.astimezone(calendar.ET).date()
    return datetime.combine(d, datetime.min.time(), calendar.ET).astimezone(timezone.utc)


def _business_days_back(now: datetime, n: int) -> datetime:
    d = now.astimezone(calendar.ET).date()
    count = 0
    while count < n - 1:
        d -= timedelta(days=1)
        if d.weekday() < 5 and d not in calendar.HOLIDAYS:
            count += 1
    return datetime.combine(d, datetime.min.time(), calendar.ET).astimezone(timezone.utc)


def count_day_trades(fills: list[dict]) -> int:
    """A day trade = buying and selling the same stock on the same (ET) day."""
    days: dict[tuple[str, str], set[str]] = {}
    for f in fills:
        day = datetime.fromisoformat(f["ts"]).astimezone(calendar.ET).date().isoformat()
        days.setdefault((f["ticker"], day), set()).add(f["side"])
    return sum(1 for sides in days.values() if sides == {"buy", "sell"})


def check(cfg: strategy.Strategy, i: Intent, ctx: Context) -> list[str]:
    """Every reason this order must not go out. Empty list = allowed."""
    r = cfg.risk
    blocks = []
    if ctx.trades_today >= r.max_trades_per_day:
        blocks.append(f"max {r.max_trades_per_day} trades/day reached")
    value = i.qty * i.price
    if i.qty <= 0:
        blocks.append("quantity is zero (position size too small for this price)")
    if value > r.max_order_usd * 1.0001:
        blocks.append(f"order ${value:,.0f} over max ${r.max_order_usd:,.0f}")
    if r.max_day_trades_per_5d >= 0 and i.side == "sell" and i.ticker in ctx.bought_today \
            and ctx.day_trades_5d >= r.max_day_trades_per_5d:
        blocks.append(f"would be day trade #{ctx.day_trades_5d + 1} in 5 days (limit {r.max_day_trades_per_5d})")
    if i.is_exit:
        return blocks  # never block a risk-reducing sell for entry-only reasons
    if ctx.halted:
        blocks.append(f"daily loss limit {r.daily_loss_limit_pct}% hit; no new buys today")
    if ctx.failed_sources > r.max_failed_sources:
        blocks.append(f"{ctx.failed_sources} data sources failing; not buying on partial data")
    if not ctx.ignore_hours and calendar.minutes_since_open(ctx.now) < r.no_trade_open_minutes:
        blocks.append(f"first {r.no_trade_open_minutes} min after open")
    if not ctx.ignore_hours and calendar.minutes_to_close(ctx.now) < r.no_trade_close_minutes:
        blocks.append(f"last {r.no_trade_close_minutes} min before close")
    if len(ctx.positions) + ctx.new_positions >= cfg.sizing.max_positions and i.ticker not in ctx.positions:
        blocks.append(f"already at {cfg.sizing.max_positions} positions")
    held = ctx.positions.get(i.ticker)
    after = ((held.qty if held else 0) + i.qty) * i.price
    if ctx.account.equity and after > ctx.account.equity * r.max_position_pct / 100:
        blocks.append(f"position would be {after / ctx.account.equity:.0%} of equity (max {r.max_position_pct}%)")
    if value > ctx.account.cash:
        blocks.append(f"not enough buying power (${ctx.account.cash:,.0f})")
    if r.avoid_wash_sales and i.ticker in ctx.loss_sales_30d:
        blocks.append("sold at a loss in the last 30 days (wash-sale rule)")
    return blocks


def plan(cfg: strategy.Strategy, ctx: Context, signals: dict, holdings_age: dict[str, float]) -> list[Intent]:
    intents = []
    eod = cfg.exit.close_at_eod and not ctx.ignore_hours and 0 <= calendar.minutes_to_close(ctx.now) < cfg.risk.no_trade_close_minutes + 5
    for t, pos in ctx.positions.items():
        sig = signals.get(t)
        price = sig.price if sig and sig.price else None
        if price is None:
            ctx.notes.append(f"no price for held {t}; exit rules skipped")
            continue
        reason = "end-of-day close" if eod else strategy.exit_reason(
            cfg, pos.avg_cost, price, sig.score if sig else None, holdings_age.get(t, 0))
        if reason:
            intents.append(Intent(t, "sell", pos.qty, price, sig.score if sig else None, [reason],
                                  is_exit=True, urgent=reason.startswith("stop-loss")))
    if not eod:
        slots = cfg.sizing.max_positions - len(ctx.positions)
        for sig in sorted(signals.values(), key=lambda s: -s.score):
            if slots <= 0:
                break
            if sig.ticker in ctx.positions:
                continue
            reasons = strategy.entry_reasons(cfg, sig)
            if reasons:
                qty = strategy.position_qty(cfg, ctx.account.equity, sig.price)
                intents.append(Intent(sig.ticker, "buy", qty, sig.price, sig.score, reasons))
                slots -= 1
    return intents


class Trader:
    def __init__(self, ledger, robinhood_factory=None):
        self.ledger = ledger
        self._robinhood_factory = robinhood_factory
        self._robinhood = None
        self.lock = asyncio.Lock()

    def cfg(self) -> strategy.Strategy:
        return strategy.load()

    def broker(self, name: str | None = None) -> Broker:
        name = name or journal.get("broker", "sim")
        if name == "robinhood":
            if self._robinhood is None:
                from app.trading.robinhood import RobinhoodBroker
                factory = self._robinhood_factory or (lambda cfg: RobinhoodBroker(cfg))
                self._robinhood = factory(self.cfg())
            return self._robinhood
        return SimBroker(self.ledger)

    def set_mode(self, mode: str, broker: str) -> None:
        if mode not in MODES or broker not in ("sim", "robinhood"):
            raise ValueError("bad mode or broker")
        if mode == "auto" and broker == "robinhood" and not settings.allow_live_auto:
            raise ValueError("Fully automatic trading on Robinhood needs ALLOW_LIVE_AUTO=1 in your .env. "
                             "Run in approve mode first.")
        if mode != "approve" or broker != journal.get("broker", "sim"):
            for p in journal.proposals("pending"):
                journal.set_proposal(p["proposal_id"], "cancelled")
                journal.update(p["id"], status="cancelled", detail="mode changed")
        journal.put("mode", mode)
        journal.put("broker", broker)

    async def kill(self) -> str:
        journal.put("kill_switch", True)
        journal.put("mode", "off")
        for p in journal.proposals("pending"):
            journal.set_proposal(p["proposal_id"], "cancelled")
            journal.update(p["id"], status="cancelled")
        try:
            msg = await self.broker().cancel_all()
        except Exception as e:  # noqa: BLE001 - the switch must flip even if the broker is unreachable
            msg = f"couldn't reach broker to cancel orders ({e}); cancel them in the Robinhood app"
        await push("Signal Desk: KILL SWITCH", f"Trading stopped. {msg}", priority="high")
        return msg

    def reset_kill(self) -> None:
        journal.put("kill_switch", False)

    async def _context(self, broker: Broker, now: datetime) -> Context:
        cfg = self.cfg()
        account, positions = await asyncio.gather(broker.account(), broker.positions())
        day_start = _et_day_start(now)
        today = now.astimezone(calendar.ET).date().isoformat()
        start_equity = journal.get(f"equity_open:{broker.name}:{today}")
        if start_equity is None:
            start_equity = account.equity
            journal.put(f"equity_open:{broker.name}:{today}", start_equity)
        halted = journal.get("halted_on") == today
        if not halted and start_equity and \
                (account.equity / start_equity - 1) * 100 <= -cfg.risk.daily_loss_limit_pct:
            halted = True
            journal.put("halted_on", today)
            await push("Signal Desk: daily loss limit",
                       f"Equity down {(1 - account.equity / start_equity) * 100:.1f}% today. New buys halted until tomorrow.",
                       priority="high")
        fills_5d = journal.executed_since(_business_days_back(now, 5))
        fills_today = [f for f in fills_5d if f["ts"] >= day_start.isoformat()]
        fills_30d = journal.executed_since(now - timedelta(days=30))
        loss_sales = set()
        for f in fills_30d:
            if f["side"] == "sell" and "loss" in (f["detail"] or ""):
                loss_sales.add(f["ticker"])
        return Context(
            now=now, account=account, positions={p.ticker: p for p in positions},
            trades_today=journal.submitted_today(day_start),
            day_trades_5d=count_day_trades(fills_5d),
            bought_today={f["ticker"] for f in fills_today if f["side"] == "buy"},
            loss_sales_30d=loss_sales,
            failed_sources=sum(1 for s in data.status.values() if not s["ok"] and s.get("checked")),
            halted=halted,
        )

    def _holdings_age(self, positions: dict) -> dict[str, float]:
        ages = {}
        fills = journal.executed_since(journal.now() - timedelta(days=365))
        for t in positions:
            buys = [f for f in fills if f["ticker"] == t and f["side"] == "buy"]
            if buys:
                ages[t] = (journal.now() - datetime.fromisoformat(buys[-1]["ts"])).total_seconds() / 86400
        return ages

    async def execute(self, broker: Broker, cfg, i: Intent, mode: str, decision_id: int | None = None) -> dict:
        band = cfg.risk.limit_band_pct / 100
        limit = round(i.price * (1 + band if i.side == "buy" else 1 - band), 2)
        if decision_id is None:
            decision_id = journal.log(broker=broker.name, mode=mode, ticker=i.ticker, side=i.side, qty=i.qty,
                                      price=i.price, limit_price=limit, score=i.score, reasons=i.reasons,
                                      status="reviewing")
        else:
            journal.update(decision_id, status="reviewing", limit_price=limit, price=i.price)
        try:
            review = await broker.review(i.ticker, i.side, i.qty, limit)
            result = await broker.place(i.ticker, i.side, i.qty, limit)
        except Exception as e:  # noqa: BLE001 - record any broker failure, never crash the loop
            journal.update(decision_id, status="error", detail=f"{type(e).__name__}: {e}"[:500])
            await push(f"Signal Desk: order failed ({i.ticker})", f"{i.side} {i.qty:g} {i.ticker}: {e}"[:300],
                       priority="high")
            return journal.decision(decision_id)
        detail = f"review: {review[:300]}"
        if i.side == "sell":
            if i.avg_cost and (result.fill_price or limit) < i.avg_cost:
                detail = "loss; " + detail
        journal.update(decision_id, status=result.status, order_id=result.order_id,
                       fill_price=result.fill_price, detail=detail[:500])
        await push(f"Signal Desk: {i.side.upper()} {i.ticker}",
                   f"{result.status}: {i.side} {i.qty:g} {i.ticker} limit ${limit:,.2f}. {'; '.join(i.reasons)}")
        return journal.decision(decision_id)

    async def cycle(self, now: datetime | None = None, force_open: bool = False) -> dict:
        async with self.lock:
            now = now or datetime.now(timezone.utc)
            summary = await self._cycle(now, force_open)
            journal.put("last_cycle", now.isoformat())
            journal.put("last_summary", summary)
            return summary

    async def _cycle(self, now: datetime, force_open: bool) -> dict:
        st = state()
        journal.expire_proposals()
        if st["kill_switch"]:
            return {"skipped": "kill switch is on"}
        if st["mode"] == "off":
            return {"skipped": "autotrader is off"}
        if not force_open and not calendar.is_open(now):
            return {"skipped": "market closed"}
        if not calendar.calendar_known(now):
            return {"skipped": "market holiday calendar needs updating for this year (app/trading/calendar.py)"}
        cfg = self.cfg()
        broker = self.broker(st["broker"])
        try:
            ctx = await self._context(broker, now)
            ctx.ignore_hours = force_open
        except Exception as e:  # noqa: BLE001
            last = journal.get("broker_alert_at")
            if not last or now - datetime.fromisoformat(last) > timedelta(hours=1):  # don't spam every cycle
                journal.put("broker_alert_at", now.isoformat())
                await push("Signal Desk: broker unavailable", str(e)[:300], priority="high")
            return {"error": f"broker: {e}"}
        sigs = {s.ticker: s for s in await engine.compute_watchlist()}
        for t in ctx.positions:
            if t not in sigs:
                sigs[t] = (await engine.compute(t))["signal"]
        intents = plan(cfg, ctx, sigs, self._holdings_age(ctx.positions))
        out = {"mode": st["mode"], "broker": broker.name, "considered": len(intents), "actions": [],
               "notes": ctx.notes, "equity": ctx.account.equity}
        for i in intents:
            if i.is_exit:
                i.avg_cost = ctx.positions[i.ticker].avg_cost  # used to tag loss sales for wash-sale tracking
            if any(p["ticker"] == i.ticker and p["side"] == i.side for p in journal.proposals("pending")):
                continue  # already waiting on you
            blocks = check(cfg, i, ctx)
            if blocks:
                journal.log(broker=broker.name, mode=st["mode"], ticker=i.ticker, side=i.side, qty=i.qty,
                            price=i.price, limit_price=None, score=i.score, reasons=i.reasons, status="blocked",
                            detail="; ".join(blocks))
                if i.urgent:
                    await push(f"Signal Desk: {i.ticker} exit blocked",
                               f"{i.reasons[0]} but blocked: {'; '.join(blocks)}. Sell manually if you choose.",
                               priority="urgent")
                out["actions"].append({"ticker": i.ticker, "side": i.side, "status": "blocked", "why": blocks})
                continue
            if st["mode"] == "approve":
                did = journal.log(broker=broker.name, mode="approve", ticker=i.ticker, side=i.side, qty=i.qty,
                                  price=i.price, limit_price=None, score=i.score, reasons=i.reasons,
                                  status="proposed")
                journal.add_proposal(did, cfg.schedule.proposal_ttl_min)
                await push(f"Signal Desk: approve {i.side} {i.ticker}?",
                           f"{i.side} {i.qty:g} {i.ticker} @ ~${i.price:,.2f}. {'; '.join(i.reasons)}. "
                           f"Open the dashboard to approve (expires in {cfg.schedule.proposal_ttl_min} min).",
                           priority="high" if i.urgent else "default")
                out["actions"].append({"ticker": i.ticker, "side": i.side, "status": "proposed"})
            else:
                d = await self.execute(broker, cfg, i, "auto")
                out["actions"].append({"ticker": i.ticker, "side": i.side, "status": d["status"]})
            ctx.trades_today += 1
            if i.side == "buy":
                ctx.new_positions += 1
                ctx.account.cash -= i.qty * i.price
        return out

    async def approve(self, proposal_id: int, now: datetime | None = None, force_open: bool = False) -> dict:
        now = now or journal.now()
        async with self.lock:
            p = next((x for x in journal.proposals("pending") if x["proposal_id"] == proposal_id), None)
            if not p:
                raise ValueError("proposal not found, already handled, or expired")
            if journal.get("kill_switch", False):
                raise ValueError("kill switch is on")
            if not force_open and not calendar.is_open(now):
                raise ValueError("market is closed; the proposal stays open until it expires")
            if p["expires"] < journal.now().isoformat():
                journal.set_proposal(proposal_id, "expired")
                raise ValueError("proposal expired; prices may have moved")
            cfg = self.cfg()
            broker = self.broker(p["broker"])
            fresh = await data.get_price(p["ticker"])
            if not fresh:
                raise ValueError(f"no current price for {p['ticker']}")
            ctx = await self._context(broker, now)
            ctx.ignore_hours = force_open
            i = Intent(p["ticker"], p["side"], p["qty"], fresh.price, p["score"], p["reasons"], is_exit=p["side"] == "sell")
            if i.is_exit and i.ticker in ctx.positions:
                i.avg_cost = ctx.positions[i.ticker].avg_cost
            blocks = check(cfg, i, ctx)
            if blocks:
                journal.set_proposal(proposal_id, "blocked")
                journal.update(p["id"], status="blocked", detail="; ".join(blocks))
                raise ValueError("risk check failed at approval time: " + "; ".join(blocks))
            journal.set_proposal(proposal_id, "approved")
            return await self.execute(broker, cfg, i, "approve", decision_id=p["id"])

    def reject(self, proposal_id: int) -> None:
        p = next((x for x in journal.proposals("pending") if x["proposal_id"] == proposal_id), None)
        if not p:
            raise ValueError("proposal not found or already handled")
        journal.set_proposal(proposal_id, "rejected")
        journal.update(p["id"], status="rejected")

    async def loop(self) -> None:
        while True:
            try:
                summary = await self.cycle()
                if summary.get("actions"):
                    log.info("autotrader: %s", summary)
            except Exception:  # noqa: BLE001 - keep running whatever happens
                log.exception("autotrader cycle failed")
            await asyncio.sleep(self.cfg().schedule.interval_min * 60)
