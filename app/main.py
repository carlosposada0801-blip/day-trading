"""FastAPI app: JSON API + static dashboard."""
import asyncio
import re
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import data, signals
from app.config import TRACKED_FUNDS, settings
from app.paper import PaperAccount, TradeError

app = FastAPI(title="Day Trading Signals", version="0.1.0")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
account = PaperAccount()

_TICKER = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


def _ticker(t: str) -> str:
    t = t.upper()
    if not _TICKER.match(t):
        raise HTTPException(400, f"invalid ticker: {t}")
    return t


async def _signal(ticker: str, moves) -> tuple:
    price, articles, posts = await asyncio.gather(
        data.get_price(ticker), data.get_news(ticker), data.get_social(ticker))
    fund_moves = [m for m in moves if m.ticker == ticker]
    return signals.build(ticker, price, articles, posts, fund_moves), price, articles, posts, fund_moves


async def _prices_for(tickers) -> dict[str, float]:
    got = await asyncio.gather(*(data.get_price(t) for t in tickers))
    return {p.ticker: p.price for p in got if p}


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def config():
    return {"watchlist": settings.watchlist, "demo_mode": settings.demo_mode,
            "funds": list(TRACKED_FUNDS), "weights": signals.WEIGHTS,
            "max_position_pct": settings.max_position_pct}


@app.get("/api/signals")
async def all_signals():
    moves = await data.get_fund_moves()
    results = await asyncio.gather(*(_signal(t, moves) for t in settings.watchlist))
    sigs = [r[0] for r in results]
    return sorted(sigs, key=lambda s: s.score, reverse=True)


@app.get("/api/ticker/{ticker}")
async def ticker_detail(ticker: str):
    t = _ticker(ticker)
    moves = await data.get_fund_moves()
    sig, price, articles, posts, fund_moves = await _signal(t, moves)
    return {"signal": sig, "closes": price.closes if price else [], "news": articles,
            "social": sorted(posts, key=lambda p: p.score, reverse=True)[:30],
            "funds": [{**m.model_dump(), "change": m.change} for m in fund_moves]}


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
