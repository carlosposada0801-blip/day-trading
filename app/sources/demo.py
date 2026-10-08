"""Deterministic synthetic data so the app runs offline and in tests.

Values are seeded by ticker + date, so they are stable within a day.
"""
import random
from datetime import date, datetime, timedelta, timezone

from app import sentiment
from app.config import TRACKED_FUNDS
from app.models import Article, FundMove, PriceInfo, SocialPost

_BASE_PRICES = {"AAPL": 228, "NVDA": 132, "TSLA": 251, "MSFT": 418, "AMD": 158, "AMZN": 186,
                "META": 589, "GOOGL": 165, "PLTR": 41, "GME": 22, "SPY": 571}

_HEADLINES = [
    "{t} beats earnings expectations as revenue surges",
    "Analyst upgrades {t} to outperform on strong growth outlook",
    "{t} shares slump after guidance warning",
    "{t} faces regulatory probe over business practices",
    "{t} announces new partnership, stock rallies",
    "{t} downgraded on valuation concerns",
    "{t} hits record high amid AI optimism",
    "{t} announces layoffs as costs rise",
    "What to watch for {t} this week",
    "{t} trading flat ahead of Fed decision",
]
_POSTS = [
    "${t} to the moon 🚀🚀 loading calls",
    "${t} is so overvalued, buying puts",
    "Just bought more ${t}, diamond hands 💎",
    "${t} breakout incoming 📈",
    "bagholding ${t} since last month 💀",
    "${t} DD: undervalued with strong growth",
    "Sold my ${t}, looks weak here 📉",
    "${t} squeeze is not over",
]


def _rng(*parts) -> random.Random:
    return random.Random("|".join(str(p) for p in (*parts, date.today().isoformat())))


def price(ticker: str) -> PriceInfo:
    rng = _rng("price", ticker)
    p = _BASE_PRICES.get(ticker, rng.uniform(20, 300))
    closes = []
    for _ in range(22):
        p *= 1 + rng.gauss(0.001, 0.02)
        closes.append(round(p, 2))
    return PriceInfo(ticker=ticker, price=closes[-1], prev_close=closes[-2], closes=closes)


def news(ticker: str) -> list[Article]:
    rng = _rng("news", ticker)
    now = datetime.now(timezone.utc)
    out = []
    for i, tpl in enumerate(rng.sample(_HEADLINES, 6)):
        title = tpl.format(t=ticker)
        out.append(Article(ticker=ticker, title=title, url="#", source="Demo Wire",
                           published=now - timedelta(hours=i * 3 + rng.random()),
                           sentiment=sentiment.score(title)))
    return out


def social(ticker: str) -> list[SocialPost]:
    rng = _rng("social", ticker)
    now = datetime.now(timezone.utc)
    out = []
    for i in range(rng.randint(4, 12)):
        text = rng.choice(_POSTS).format(t=ticker)
        out.append(SocialPost(ticker=ticker, text=text, url="#", platform="demo",
                              author=f"trader{rng.randint(1, 999)}", score=rng.randint(0, 500),
                              created=now - timedelta(minutes=i * 17), sentiment=sentiment.score(text)))
    return out


def fund_moves(tickers: list[str]) -> list[FundMove]:
    out = []
    for fund in TRACKED_FUNDS:
        rng = _rng("fund", fund)
        for t in rng.sample(tickers, k=min(3, len(tickers))):
            prev = rng.choice([0, rng.randint(100_000, 5_000_000)])
            shares = max(0, int(prev * rng.uniform(0.3, 1.8)) if prev else rng.randint(50_000, 1_000_000))
            out.append(FundMove(fund=fund, ticker=t, issuer=t, shares=shares, prev_shares=prev,
                                value_usd=int(shares * price(t).price), period="demo"))
    return out
