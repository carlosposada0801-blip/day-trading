"""FastAPI app: JSON API + static dashboard, locked to a single user."""
import asyncio
import contextlib
import re
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import alerts, auth, backtest, data, engine, signals, store
from app.config import TRACKED_FUNDS, settings
from app.paper import PaperAccount, TradeError
from app.trading import calendar as market
from app.trading import autopilot, journal, penny, simulate
from app.trading import strategy as strategy_cfg
from app.trading.robinhood import CALLBACK_PATH
from app.trading.robinhood import login as rh_login
from app.trading.trader import Trader
from app.trading.trader import state as trader_state


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    saved = journal.get("watchlist")
    if saved:  # a watchlist edited in the dashboard overrides WATCHLIST from .env
        settings.watchlist[:] = saved
    tasks = []
    if settings.alerts_enabled:
        tasks.append(asyncio.create_task(alerts.loop()))
    if settings.trader_enabled:
        tasks.append(asyncio.create_task(trader.loop()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Signal Desk", version="0.2.0", lifespan=lifespan)
app.middleware("http")(auth.middleware)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
account = PaperAccount()
trader = Trader(account)

_TICKER = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


def _ticker(t: str) -> str:
    t = t.upper()
    if not _TICKER.match(t):
        raise HTTPException(400, f"invalid ticker: {t}")
    return t


async def _prices_for(tickers) -> dict[str, float]:
    got = await asyncio.gather(*(data.get_price(t) for t in tickers))
    return {p.ticker: p.price for p in got if p}


# ---- login -------------------------------------------------------------------------------

@app.get("/login")
async def login_page():
    return FileResponse(STATIC / "login.html")


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    ip = request.client.host if request.client else "?"
    if auth.locked_out(ip):
        return RedirectResponse("/login?error=locked", status_code=303)
    if not auth.check_password(ip, password):
        return RedirectResponse("/login?error=1", status_code=303)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.SESSION_DAYS * 86400, httponly=True,
                    samesite="strict", secure=request.url.scheme == "https")
    return resp


@app.post("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE)
    return resp


# ---- dashboard ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def config():
    return {"watchlist": settings.watchlist, "demo_mode": settings.demo_mode,
            "funds": list(TRACKED_FUNDS), "weights": signals.WEIGHTS,
            "max_position_pct": settings.max_position_pct, "ai_sentiment": settings.ai_sentiment,
            "ai_model": settings.ai_model if settings.ai_sentiment else None,
            "alerts": {"enabled": settings.alerts_enabled, "every_min": settings.alert_interval_min,
                       "delta": settings.alert_delta, "push": bool(settings.alert_webhook_url)}}


@app.get("/api/signals")
async def all_signals():
    return sorted(await engine.compute_watchlist(), key=lambda s: s.score, reverse=True)


@app.get("/api/ticker/{ticker}")
async def ticker_detail(ticker: str):
    r = await engine.compute(_ticker(ticker))
    return {"signal": r["signal"], "closes": r["price"].closes if r["price"] else [],
            "dates": r["price"].dates if r["price"] else [], "news": r["news"],
            "social": sorted(r["social"], key=lambda p: p.score, reverse=True)[:30],
            "funds": [{**m.model_dump(), "change": m.change} for m in r["funds"]],
            "insiders": sorted(({**t.model_dump(), "value": t.value} for t in r["insiders"]),
                               key=lambda t: t["date"], reverse=True),
            "congress": [t.model_dump() for t in r["congress"]],
            "history": store.history(r["signal"].ticker, since_hours=24 * 30)}


class WatchlistIn(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=30)


@app.put("/api/watchlist")
async def set_watchlist(w: WatchlistIn):
    tickers = list(dict.fromkeys(_ticker(t.strip()) for t in w.tickers if t.strip()))
    if not tickers:
        raise HTTPException(400, "watchlist can't be empty")
    settings.watchlist[:] = tickers  # mutate in place: every module reads this same list
    journal.put("watchlist", tickers)
    return {"watchlist": tickers}


@app.get("/api/trending")
async def trending():
    return await data.get_trending()


@app.get("/api/funds")
async def funds():
    """Biggest position changes across tracked funds' latest 13F filings."""
    moves = await data.get_fund_moves()
    rows = [{**m.model_dump(), "change": m.change} for m in moves if m.change]
    return sorted(rows, key=lambda r: abs(r["change"]) * (r["value_usd"] / max(r["shares"], 1)),
                  reverse=True)[:40]


@app.get("/api/sources")
async def sources():
    return {"demo_mode": settings.demo_mode, "sources": data.status}


# ---- alerts ------------------------------------------------------------------------------

@app.get("/api/alerts")
async def list_alerts():
    rows = store.alerts()
    return {"alerts": rows, "unseen": sum(1 for a in rows if not a["seen"])}


@app.post("/api/alerts/seen")
async def alerts_seen():
    store.mark_alerts_seen()
    return {"ok": True}


@app.post("/api/alerts/run")
async def alerts_run():
    """Score the watchlist now instead of waiting for the next scheduled cycle."""
    return {"new": await alerts.run_cycle()}


# ---- backtest ----------------------------------------------------------------------------

@app.get("/api/backtest")
async def run_backtest(horizon: int = 5):
    if not 1 <= horizon <= 60:
        raise HTTPException(400, "horizon must be 1-60 trading days")
    hist = await asyncio.gather(*(data.get_history(t) for t in settings.watchlist))
    prices = {p.ticker: p for p in hist if p}
    momentum = [s for p in prices.values() for s in backtest.momentum_backtest(p, horizon)]
    snapshots = store.history()
    return {
        "horizon_days": horizon,
        "track_record": backtest.track_record(snapshots, prices, horizon),
        "snapshots": len(snapshots),
        "momentum": backtest.evaluate(momentum),
        "demo": settings.demo_mode,
    }


# ---- paper trading -----------------------------------------------------------------------

class OrderIn(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    qty: float = Field(gt=0)
    note: str = ""


async def _account_prices() -> dict[str, float]:
    held = {p["ticker"] for p in account.summary({})["positions"]}
    return await _prices_for(held)


@app.get("/api/paper")
async def paper_summary():
    return {**account.summary(await _account_prices()), "trades": account.trades()[:50]}


@app.post("/api/paper/order")
async def paper_order(o: OrderIn):
    t = _ticker(o.ticker)
    price = await data.get_price(t)
    if not price:
        raise HTTPException(503, f"no price available for {t}")
    try:
        return account.order(t, o.side, o.qty, price.price, await _account_prices(), o.note)
    except TradeError as e:
        raise HTTPException(400, str(e))


@app.post("/api/paper/reset")
async def paper_reset():
    account.reset()
    return {"ok": True}


# ---- autotrader --------------------------------------------------------------------------

_connect_task: asyncio.Task | None = None
_connect_result: dict = {}


@app.get("/api/trading")
async def trading_status():
    cfg = strategy_cfg.load()
    st = trader_state()
    rh = trader._robinhood
    return {
        **st,
        "market_open": market.is_open(),
        "allow_live_auto": settings.allow_live_auto,
        "proposals": journal.proposals("pending"),
        "decisions": journal.decisions(40),
        "robinhood": {
            "connected": bool(rh and rh.tools),
            "tools": sorted(rh.tools) if rh else [],
            "login_url": rh_login.url,
            "connecting": bool(_connect_task and not _connect_task.done()),
            "last_connect": _connect_result,
        },
        "rules": {"entry": vars(cfg.entry), "exit": vars(cfg.exit), "sizing": vars(cfg.sizing),
                  "risk": vars(cfg.risk), "schedule": vars(cfg.schedule)},
    }


class ModeIn(BaseModel):
    mode: Literal["off", "approve", "auto"]
    broker: Literal["sim", "robinhood"]


@app.post("/api/trading/mode")
async def trading_mode(m: ModeIn):
    try:
        trader.set_mode(m.mode, m.broker)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return trader_state()


@app.post("/api/trading/kill")
async def trading_kill():
    return {"message": await trader.kill(), **trader_state()}


@app.post("/api/trading/resume")
async def trading_resume():
    trader.reset_kill()
    return trader_state()


@app.post("/api/trading/run")
async def trading_run():
    """Run one cycle now. In demo mode it ignores market hours so you can try it any time."""
    return await trader.cycle(force_open=settings.demo_mode)


@app.post("/api/trading/proposals/{proposal_id}/approve")
async def proposal_approve(proposal_id: int):
    try:
        return await trader.approve(proposal_id, force_open=settings.demo_mode)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/trading/proposals/{proposal_id}/reject")
async def proposal_reject(proposal_id: int):
    try:
        trader.reject(proposal_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/trading/journal.csv")
async def journal_csv():
    return PlainTextResponse(journal.csv_export(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=trade-journal.csv"})


@app.get("/api/trading/backtest")
async def trading_backtest(source: Literal["momentum", "recorded"] = "momentum", cost_bps: float = 10):
    cfg = strategy_cfg.load()
    hist = await asyncio.gather(*(data.get_history(t) for t in settings.watchlist), data.get_history("SPY"))
    prices = {p.ticker: p for p in hist[:-1] if p}
    if source == "momentum":
        scores = {t: simulate.momentum_scores(p) for t, p in prices.items()}
    else:
        scores = simulate.recorded_scores(store.history())
    r = simulate.run(scores, prices, cfg, benchmark=hist[-1], cost_bps=cost_bps)
    return {**r, "source": source, "demo": settings.demo_mode}


async def _do_connect():
    global _connect_result
    try:
        tools = await trader.broker("robinhood").connect()
        _connect_result = {"ok": True, "tools": tools}
    except Exception as e:  # noqa: BLE001 - surface any login/connection failure in the dashboard
        _connect_result = {"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}


@app.post("/api/broker/robinhood/connect")
async def robinhood_connect():
    global _connect_task
    if not (_connect_task and not _connect_task.done()):
        _connect_task = asyncio.create_task(_do_connect())
    await asyncio.sleep(1.5)  # give the OAuth flow a moment to produce the login URL
    return {"login_url": rh_login.url, "result": _connect_result}


@app.post("/api/broker/robinhood/disconnect")
async def robinhood_disconnect():
    if trader._robinhood:
        trader._robinhood.disconnect()
    if journal.get("broker") == "robinhood":
        trader.set_mode("off", "sim")
    return {"ok": True}


@app.get(CALLBACK_PATH)
async def robinhood_callback(request: Request):
    if not rh_login.complete(request.url.query):
        raise HTTPException(400, "no Robinhood login in progress")
    return HTMLResponse("<p style='font-family:system-ui'>Robinhood connected. You can close this tab "
                        "and return to <a href='/'>Signal Desk</a>.</p>")


# ---- autopilot -----------------------------------------------------------------------------

async def _preflight(broker_name: str) -> tuple[list[dict], dict | None]:
    """Checks before going hands-off. 'block' items must pass; 'warn' items are your call."""
    items: list[dict] = []

    def add(ok: bool, level: str, text: str, fix: str = ""):
        items.append({"ok": ok, "level": level, "text": text, "fix": "" if ok else fix})

    acct = None
    try:
        a = await trader.broker(broker_name).account()
        acct = {"equity": a.equity, "cash": a.cash}
    except Exception as e:  # noqa: BLE001
        add(False, "block", "Broker reachable", f"{e}"[:200])
    else:
        add(True, "block", "Broker reachable")
        add(a.equity > 0, "block", "Account has money in it", "Deposit into the account first.")
    live = broker_name == "robinhood"
    if live:
        add(settings.allow_live_auto, "block", "Live automatic trading allowed (ALLOW_LIVE_AUTO=1)",
            "Add ALLOW_LIVE_AUTO=1 to .env and restart, once you're comfortable.")
    add(bool(settings.alert_webhook_url), "block" if live else "warn", "Phone notifications set up",
        "Set ALERT_WEBHOOK_URL (ntfy) so you hear about deposits, profits and problems.")
    add(not journal.get("kill_switch", False), "block", "Kill switch off", "Click Resume in the Autotrader panel.")
    add(market.calendar_known(), "block", "Market calendar covers this year", "Update app/trading/calendar.py.")
    cfg = strategy_cfg.load()
    try:
        hist = await asyncio.gather(*(data.get_history(t) for t in settings.watchlist), data.get_history("SPY"))
        prices = {p.ticker: p for p in hist[:-1] if p}
        r = simulate.run({t: simulate.momentum_scores(p) for t, p in prices.items()}, prices, cfg, benchmark=hist[-1])
        beats = r.get("beats_benchmark")
        add(bool(beats), "warn", "Signal rules beat holding SPY in the backtest",
            f"Strategy {r.get('total_return_pct')}% vs SPY {r.get('benchmark_return_pct')}%. "
            f"Consider a bigger core_pct in strategy.toml.")
    except Exception as e:  # noqa: BLE001
        add(False, "warn", "Backtest ran", f"{e}"[:200])
    if cfg.penny.enabled:
        add(False, "warn", f"Penny stocks on ({cfg.penny.budget_pct:.0f}% of money)",
            "High risk: big swings, thin trading, pump-and-dumps. Guardrails apply but losses can be fast.")
    add(False, "warn", "App runs on an always-on machine",
        "Exits and deposits are only handled while the app runs. See README: Running it all the time.")
    return items, acct


@app.get("/api/autopilot")
async def autopilot_status():
    st = trader_state()
    cfg = strategy_cfg.load()
    items, acct = await _preflight(st["broker"])
    f = autopilot.load(st["broker"])
    alloc = None
    if acct:
        try:
            positions = await trader.broker(st["broker"]).positions()
            prices = await _prices_for([p.ticker for p in positions])
            core = cfg.autopilot.core_symbol.upper()
            pennies = penny.held()
            core_v = sum(p.qty * prices.get(p.ticker, p.avg_cost) for p in positions if p.ticker == core)
            sat_v = sum(p.qty * prices.get(p.ticker, p.avg_cost) for p in positions if p.ticker != core)
            pen_v = sum(p.qty * prices.get(p.ticker, p.avg_cost) for p in positions if p.ticker in pennies)
            reserved = f.reserved if f else 0.0
            alloc = {"core": round(core_v, 2), "satellites": round(sat_v, 2), "penny": round(pen_v, 2),
                     "set_aside": round(min(reserved, acct["cash"]), 2),
                     "cash": round(max(0.0, acct["cash"] - reserved), 2)}
        except Exception:  # noqa: BLE001 - status still useful without the breakdown
            alloc = None
    return {
        "running": st["mode"] == "auto" and not st["kill_switch"],
        "broker": st["broker"],
        "account": acct,
        "net_deposits": f.net_deposits if f else None,
        "profit": round(f.profit(acct["equity"]), 2) if f and acct else None,
        "reserved": f.reserved if f else 0.0,
        "set_aside_total": f.set_aside_total if f else 0.0,
        "allocation": alloc,
        "plan": vars(cfg.autopilot),
        "penny_plan": {"enabled": cfg.penny.enabled, "budget_pct": cfg.penny.budget_pct},
        "fractional": cfg.sizing.fractional,
        "last_deposit": journal.get(f"ap:{st['broker']}:last_deposit_ts"),
        "deposit_overdue_days": autopilot.deposit_overdue(cfg, st["broker"], journal.now()),
        "checks": items,
        "ready": all(i["ok"] for i in items if i["level"] == "block"),
    }


@app.post("/api/autopilot/start")
async def autopilot_start():
    st = trader_state()
    items, _ = await _preflight(st["broker"])
    blockers = [i["text"] + (f": {i['fix']}" if i["fix"] else "") for i in items if i["level"] == "block" and not i["ok"]]
    if blockers:
        raise HTTPException(400, "Can't start autopilot yet. " + " | ".join(blockers))
    try:
        trader.set_mode("auto", st["broker"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"running": True}


@app.post("/api/autopilot/stop")
async def autopilot_stop():
    trader.set_mode("off", trader_state()["broker"])
    return {"running": False}


@app.post("/api/autopilot/release")
async def autopilot_release():
    """Keep the set-aside profit invested instead of withdrawing it."""
    return {"released": autopilot.release(trader_state()["broker"])}


class TransferIn(BaseModel):
    amount: float  # zero is rejected by the ledger


@app.post("/api/paper/transfer")
async def paper_transfer(t: TransferIn):
    """Simulated deposit (+) or withdrawal (-) for the practice account."""
    try:
        return {"cash": account.transfer(t.amount)}
    except TradeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/penny")
async def penny_scan():
    cfg = strategy_cfg.load()
    rows = await penny.scan(cfg) if cfg.penny.enabled else []
    return {"enabled": cfg.penny.enabled, "rules": vars(cfg.penny), "held": sorted(penny.held()),
            "candidates": [{**{k: v for k, v in r.items() if k != "signal"},
                            "score": r["signal"].score, "confidence": r["signal"].confidence} for r in rows]}
