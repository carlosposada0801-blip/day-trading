"""Compute a ticker's full signal from every source. Shared by the API and the alert loop."""
import asyncio

from app import ai, data, signals
from app.config import settings


async def compute(ticker: str, moves=None) -> dict:
    if moves is None:
        moves = await data.get_fund_moves()
    price, articles, posts, insider_trades, congress_trades = await asyncio.gather(
        data.get_price(ticker), data.get_news(ticker), data.get_social(ticker),
        data.get_insiders(ticker), data.get_congress(ticker))
    used_ai = settings.ai_sentiment and await ai.rescore(ticker, articles, posts)
    fund_moves = [m for m in moves if m.ticker == ticker]
    sig = signals.build(ticker, price, articles, posts, fund_moves, insider_trades, congress_trades, ai=used_ai)
    return {"signal": sig, "price": price, "news": articles, "social": posts, "funds": fund_moves,
            "insiders": insider_trades, "congress": congress_trades}


async def compute_watchlist() -> list:
    moves = await data.get_fund_moves()
    results = await asyncio.gather(*(compute(t, moves) for t in settings.watchlist))
    return [r["signal"] for r in results]
