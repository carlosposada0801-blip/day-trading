"""Blend news, social, insider, fund, congressional and momentum signals into one score per ticker."""
import math
from datetime import date, datetime, timedelta, timezone

from app.models import Article, CongressTrade, FundMove, InsiderTrade, PriceInfo, Signal, SocialPost

WEIGHTS = {"news": 0.30, "social": 0.25, "momentum": 0.15, "insiders": 0.15, "funds": 0.10, "congress": 0.05}
STANCE_THRESHOLD = 20  # |score| above this is labelled bullish/bearish


def _recency_weight(ts: datetime | None, half_life_hours: float) -> float:
    if ts is None:
        return 0.5
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_h = max(0.0, (datetime.now(timezone.utc) - ts) / timedelta(hours=1))
    return 0.5 ** (age_h / half_life_hours)


def news_component(articles: list[Article]) -> float | None:
    pairs = [(a.sentiment, _recency_weight(a.published, 12)) for a in articles]
    total = sum(w for _, w in pairs)
    return sum(s * w for s, w in pairs) / total if total else None


def social_component(posts: list[SocialPost]) -> float | None:
    # Newer and more-upvoted posts count more; log keeps one viral post from dominating.
    pairs = [(p.sentiment, _recency_weight(p.created, 6) * (1 + math.log1p(max(p.score, 0))))
             for p in posts]
    total = sum(w for _, w in pairs)
    return sum(s * w for s, w in pairs) / total if total else None


def funds_component(moves: list[FundMove]) -> float | None:
    """Each fund votes +1 for a new/increased position, -1 for a cut/exit, scaled by size of change."""
    votes = []
    for m in moves:
        if m.prev_shares == 0 and m.shares == 0:
            continue
        rel = m.change / max(m.prev_shares, 1) if m.prev_shares else 1.0
        votes.append(math.tanh(rel * 2))
    return sum(votes) / len(votes) if votes else None


def momentum_component(price: PriceInfo | None) -> float | None:
    if not price or len(price.closes) < 6:
        return None
    ret5 = price.closes[-1] / price.closes[-6] - 1
    return math.tanh(ret5 / 0.05)  # a 5% weekly move ~ 0.76


def _days_ago(iso: str) -> float:
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except ValueError:
        return 90.0


def insiders_component(trades: list[InsiderTrade]) -> float | None:
    """Net open-market buying by insiders over ~90 days. Sales count a quarter as much as buys,
    because insiders sell for many non-informative reasons."""
    recent = [t for t in trades if _days_ago(t.date) <= 90 and t.value > 0]
    if not recent:
        return None
    buys = sum(t.value for t in recent if t.code == "P")
    sells = sum(t.value for t in recent if t.code == "S")
    return math.tanh((buys - 0.25 * sells) / 500_000)


def congress_component(trades: list[CongressTrade]) -> float | None:
    recent = [t for t in trades if _days_ago(t.traded) <= 120]
    if not recent:
        return None
    net = sum(t.amount_mid * (1 if t.side == "buy" else -1) for t in recent)
    return math.tanh(net / 100_000)


def build(ticker: str, price: PriceInfo | None, articles: list[Article],
          posts: list[SocialPost], moves: list[FundMove],
          insiders: list[InsiderTrade] = (), congress: list[CongressTrade] = (), ai: bool = False) -> Signal:
    comps = {
        "news": news_component(articles),
        "social": social_component(posts),
        "momentum": momentum_component(price),
        "insiders": insiders_component(list(insiders)),
        "funds": funds_component(moves),
        "congress": congress_component(list(congress)),
    }
    available = {k: v for k, v in comps.items() if v is not None}
    wsum = sum(WEIGHTS[k] for k in available)
    score = 100 * sum(WEIGHTS[k] * v for k, v in available.items()) / wsum if wsum else 0.0
    # Confidence grows with how many sources reported and how much data they had.
    volume = min(1.0, (len(articles) + len(posts)) / 30)
    confidence = round(wsum * (0.5 + 0.5 * volume), 2)
    stance = "bullish" if score > STANCE_THRESHOLD else "bearish" if score < -STANCE_THRESHOLD else "neutral"
    return Signal(
        ticker=ticker,
        price=price.price if price else None,
        change_pct=round(price.change_pct, 2) if price else None,
        score=round(score, 1), stance=stance, confidence=confidence,
        components={k: (round(v, 3) if v is not None else None) for k, v in comps.items()},
        counts={"news": len(articles), "social": len(posts), "funds": len(moves),
                "insiders": len(insiders), "congress": len(congress)},
        ai=ai,
    )
