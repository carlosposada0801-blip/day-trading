"""Deterministic synthetic data so the app runs offline and in tests.

Values are seeded by ticker + date, so they are stable within a day.
"""
import random
from datetime import date, datetime, timedelta, timezone

from app import sentiment
from app.config import TRACKED_FUNDS
from app.models import Article, CongressTrade, FundMove, InsiderTrade, PriceInfo, SocialPost

_BASE_PRICES = {"AAPL": 228, "NVDA": 132, "TSLA": 251, "MSFT": 418, "AMD": 158, "AMZN": 186,
                "META": 589, "GOOGL": 165, "PLTR": 41, "GME": 22, "SPY": 571, "VOO": 525}

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


# Made-up penny tickers that exercise each penny-stock guardrail in demo mode:
# (price, typical daily shares, exchange, 5-day run-up)
DEMO_PENNIES = {
    "PNYA": (1.85, 4_000_000, "NasdaqCM", 0.0),   # liquid, listed: can be bought
    "PNYB": (3.40, 60_000, "NasdaqCM", 0.0),      # too thinly traded
    "OTCX": (0.42, 9_000_000, "PNK", 0.0),        # over-the-counter: blocked
    "PUMP": (2.10, 30_000_000, "NasdaqCM", 0.9),  # +90% in 5 days on hype: pump guard
}


def price(ticker: str, days: int = 22) -> PriceInfo:
    rng = _rng("price", ticker)
    penny = DEMO_PENNIES.get(ticker)
    p = penny[0] if penny else _BASE_PRICES.get(ticker, rng.uniform(20, 300))
    vol = penny[1] if penny else rng.uniform(5e6, 6e7)
    vol_sd = 0.06 if penny else 0.02
    # Walk backwards from the base price so the latest close stays near it whatever `days` is.
    closes = [p]
    for k in range(days - 1):
        step = rng.gauss(0.001, vol_sd)
        if penny and penny[3] and k < 5:  # recent run-up for the pump example
            step = (1 + penny[3]) ** (1 / 5) - 1
        closes.append(closes[-1] / (1 + step))
    digits = 4 if p < 1 else 2
    closes = [round(c, digits) for c in reversed(closes)]
    volumes = [round(vol * rng.uniform(0.6, 1.4)) for _ in closes]
    if penny and penny[3]:
        volumes[-5:] = [v * 8 for v in volumes[-5:]]
    today = date.today()
    dates = [(today - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    return PriceInfo(ticker=ticker, price=closes[-1], prev_close=closes[-2], closes=closes, dates=dates,
                     volumes=volumes, exchange=penny[2] if penny else "NasdaqGS")


def news(ticker: str) -> list[Article]:
    if ticker == "PUMP":
        return []  # pumps run on hype, not news
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
    if ticker == "PUMP":
        for i in range(40):
            text = rng.choice(["$PUMP to the moon 🚀🚀🚀 next 10 bagger", "$PUMP squeeze incoming, load up 🚀",
                               "$PUMP breakout, don't miss this 📈"])
            out.append(SocialPost(ticker=ticker, text=text, url="#", platform="demo", author=f"newacct{i}",
                                  score=rng.randint(50, 900), created=now - timedelta(minutes=i * 7),
                                  sentiment=sentiment.score(text)))
        return out
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


_INSIDERS = [("Jane Rivera", "CEO"), ("Mark Chen", "CFO"), ("Priya Shah", "Director"), ("Tom Okafor", "COO")]
_MEMBERS = [("Rep. A. Example", "House"), ("Sen. B. Sample", "Senate"), ("Rep. C. Demo", "House")]


def insiders(ticker: str) -> list[InsiderTrade]:
    rng = _rng("insider", ticker)
    px = price(ticker).price
    out = []
    for i in range(rng.randint(0, 4)):
        name, title = rng.choice(_INSIDERS)
        out.append(InsiderTrade(ticker=ticker, insider=name, title=title, code=rng.choice("PSS"),
                                shares=rng.randint(1_000, 40_000), price=round(px * rng.uniform(0.9, 1.05), 2),
                                date=(date.today() - timedelta(days=rng.randint(1, 60))).isoformat(), url="#"))
    return out


def congress(ticker: str) -> list[CongressTrade]:
    rng = _rng("congress", ticker)
    out = []
    for _ in range(rng.randint(0, 3)):
        name, chamber = rng.choice(_MEMBERS)
        low, high = rng.choice([(1_001, 15_000), (15_001, 50_000), (50_001, 100_000), (100_001, 250_000)])
        traded = date.today() - timedelta(days=rng.randint(10, 80))
        out.append(CongressTrade(ticker=ticker, member=name, chamber=chamber, side=rng.choice(["buy", "sell"]),
                                 amount_low=low, amount_high=high, traded=traded.isoformat(),
                                 disclosed=(traded + timedelta(days=30)).isoformat(), url="#"))
    return out
