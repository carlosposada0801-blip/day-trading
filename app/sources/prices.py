"""Price history from Yahoo Finance's public chart endpoint."""
from app.models import PriceInfo
from app.sources.http import client


def parse_chart(data: dict, ticker: str) -> PriceInfo:
    res = data["chart"]["result"][0]
    meta = res["meta"]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    price = meta.get("regularMarketPrice") or closes[-1]
    prev = meta.get("chartPreviousClose") if len(closes) < 2 else closes[-2]
    return PriceInfo(ticker=ticker, price=price, prev_close=prev or price, closes=closes)


async def fetch(ticker: str) -> PriceInfo:
    async with client() as c:
        r = await c.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d")
        r.raise_for_status()
        return parse_chart(r.json(), ticker)
