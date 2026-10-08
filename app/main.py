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
from app.trading import journal, simulate
from app.trading import strategy as strategy_cfg
from app.trading.robinhood import CALLBACK_PATH
from app.trading.robinhood import login as rh_login
from app.trading.trader import Trader
from app.trading.trader import state as trader_state


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
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
    return {"signal": r["signal"], "closes": r["price"].closes if r["price"] else [], "news": r["news"],
            "social": sorted(r["social"], key=lambda p: p.score, reverse=True)[:30],
            "funds": [{**m.model_dump(), "change": m.change} for m in r["funds"]],
            "insiders": sorted(({**t.model_dump(), "value": t.value} for t in r["insiders"]),
                               key=lambda t: t["date"], reverse=True),
            "congress": [t.model_dump() for t in r["congress"]],
            "history": store.history(r["signal"].ticker, since_hours=24 * 30)}


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
