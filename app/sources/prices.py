"""Price history from Yahoo Finance's public chart endpoint."""
from datetime import datetime, timezone

from app.models import PriceInfo
from app.sources.http import client


def parse_chart(data: dict, ticker: str) -> PriceInfo:
    res = data["chart"]["result"][0]
    meta = res["meta"]
    raw = res["indicators"]["quote"][0]["close"]
    stamps = res.get("timestamp") or [None] * len(raw)
    pairs = [(t, c) for t, c in zip(stamps, raw) if c is not None]
    closes = [c for _, c in pairs]
    dates = [datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat() if t else "" for t, _ in pairs]
    price = meta.get("regularMarketPrice") or closes[-1]
    prev = meta.get("chartPreviousClose") if len(closes) < 2 else closes[-2]
    return PriceInfo(ticker=ticker, price=price, prev_close=prev or price, closes=closes, dates=dates)


async def fetch(ticker: str, range_: str = "1mo") -> PriceInfo:
    async with client() as c:
        r = await c.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_}&interval=1d")
        r.raise_for_status()
        return parse_chart(r.json(), ticker)
