"""Price history from Yahoo Finance's public chart endpoint."""
from datetime import datetime, timezone

from app.models import PriceInfo
from app.sources.http import client


def parse_chart(data: dict, ticker: str) -> PriceInfo:
    res = data["chart"]["result"][0]
    meta = res["meta"]
    quote = res["indicators"]["quote"][0]
    raw = quote["close"]
    vols = quote.get("volume") or [None] * len(raw)
    stamps = res.get("timestamp") or [None] * len(raw)
    rows = [(t, c, v) for t, c, v in zip(stamps, raw, vols) if c is not None]
    closes = [c for _, c, _ in rows]
    volumes = [float(v or 0) for _, _, v in rows] if quote.get("volume") else []
    dates = [datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat() if t else "" for t, _, _ in rows]
    price = meta.get("regularMarketPrice") or closes[-1]
    prev = meta.get("chartPreviousClose") if len(closes) < 2 else closes[-2]
    return PriceInfo(ticker=ticker, price=price, prev_close=prev or price, closes=closes, dates=dates,
                     volumes=volumes, exchange=meta.get("exchangeName") or meta.get("fullExchangeName") or "")


async def fetch(ticker: str, range_: str = "1mo") -> PriceInfo:
    async with client() as c:
        r = await c.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_}&interval=1d")
        r.raise_for_status()
        return parse_chart(r.json(), ticker)
