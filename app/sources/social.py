"""Social chatter from Reddit and StockTwits public endpoints."""
from datetime import datetime, timezone

from app import sentiment
from app.config import settings
from app.models import SocialPost
from app.sources.http import client


def parse_stocktwits(data: dict, ticker: str) -> list[SocialPost]:
    out = []
    for m in data.get("messages", []):
        label = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        label = label.lower() if label in ("Bullish", "Bearish") else None
        text = m.get("body", "")
        s = sentiment.score(text)
        if label:  # the author told us their stance; trust it over the lexicon
            s = 0.75 if label == "bullish" else -0.75
        out.append(SocialPost(
            ticker=ticker, text=text, platform="stocktwits",
            url=f"https://stocktwits.com/{(m.get('user') or {}).get('username', '')}/message/{m.get('id')}",
            author=(m.get("user") or {}).get("username", ""),
            score=((m.get("likes") or {}).get("total") or 0),
            created=m.get("created_at"), sentiment=s, label=label,
        ))
    return out


def parse_reddit(data: dict, known: set[str]) -> list[SocialPost]:
    """Turn a subreddit listing into posts, one per ticker mentioned."""
    out = []
    for child in data.get("data", {}).get("children", []):
        p = child.get("data", {})
        text = f"{p.get('title', '')} {p.get('selftext', '')[:1000]}"
        for t in sentiment.extract_tickers(text, known):
            out.append(SocialPost(
                ticker=t, text=p.get("title", ""), platform="reddit",
                url="https://reddit.com" + p.get("permalink", ""),
                author=p.get("author", ""), score=int(p.get("score", 0)),
                created=datetime.fromtimestamp(p.get("created_utc", 0), tz=timezone.utc),
                sentiment=sentiment.score(text),
            ))
    return out


async def fetch_stocktwits(ticker: str) -> list[SocialPost]:
    async with client() as c:
        r = await c.get(f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json")
        r.raise_for_status()
        return parse_stocktwits(r.json(), ticker)


async def fetch_reddit(known: set[str]) -> list[SocialPost]:
    posts: list[SocialPost] = []
    async with client() as c:
        for sub in settings.subreddits:
            r = await c.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=100")
            r.raise_for_status()
            posts += parse_reddit(r.json(), known)
    return posts
