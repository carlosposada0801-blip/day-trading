"""News headlines from public RSS feeds (Yahoo Finance + Google News)."""
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from app import sentiment
from app.models import Article
from app.sources.http import client

FEEDS = {
    "Yahoo Finance": "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US",
    "Google News": "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
}


def parse_rss(xml_text: str, ticker: str, source: str) -> list[Article]:
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        pub = item.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub) if pub else None
        except (TypeError, ValueError):
            published = None
        out.append(Article(
            ticker=ticker, title=title, url=(item.findtext("link") or "").strip(),
            source=source, published=published, sentiment=sentiment.score(title),
        ))
    return out


async def fetch(ticker: str, limit: int = 20) -> list[Article]:
    articles: list[Article] = []
    seen: set[str] = set()
    async with client() as c:
        for source, url in FEEDS.items():
            r = await c.get(url.format(t=ticker, q=quote_plus(f"{ticker} stock")))
            r.raise_for_status()
            for a in parse_rss(r.text, ticker, source):
                key = a.title.lower()[:80]
                if key not in seen:
                    seen.add(key)
                    articles.append(a)
    articles.sort(key=lambda a: a.published.timestamp() if a.published else 0, reverse=True)
    return articles[:limit]
