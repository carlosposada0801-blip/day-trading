"""Fetch from every source with caching and per-source error isolation.

One source failing (rate limit, outage, blocked network) never breaks the
dashboard; its status is reported instead and the signal uses what's left.
"""
import asyncio
import logging
from datetime import datetime, timezone

from app import cache
from app.config import settings
from app.models import Article, FundMove, PriceInfo, SocialPost
from app.sources import demo, news, portfolios, prices, social

log = logging.getLogger(__name__)
status: dict[str, dict] = {}


async def _safe(name: str, key: str, ttl: int, fn, default):
    try:
        value = await cache.cached(key, ttl, fn)
        status[name] = {"ok": True, "error": None, "checked": datetime.now(timezone.utc).isoformat()}
        return value
    except Exception as e:  # noqa: BLE001 - any source failure degrades gracefully
        log.warning("source %s failed: %s", name, e)
        status[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200],
                        "checked": datetime.now(timezone.utc).isoformat()}
        return default


async def get_price(ticker: str) -> PriceInfo | None:
    if settings.demo_mode:
        return demo.price(ticker)
    return await _safe("prices", f"price:{ticker}", 60, lambda: prices.fetch(ticker), None)


async def get_news(ticker: str) -> list[Article]:
    if settings.demo_mode:
        return demo.news(ticker)
    return await _safe("news", f"news:{ticker}", settings.cache_ttl, lambda: news.fetch(ticker), [])


async def get_social(ticker: str) -> list[SocialPost]:
    if settings.demo_mode:
        return demo.social(ticker)
    known = set(settings.watchlist) | {ticker}
    st, rd = await asyncio.gather(
        _safe("stocktwits", f"st:{ticker}", settings.cache_ttl, lambda: social.fetch_stocktwits(ticker), []),
        _safe("reddit", "reddit", settings.cache_ttl, lambda: social.fetch_reddit(known), []),
    )
    return st + [p for p in rd if p.ticker == ticker]


async def get_trending() -> list[dict]:
    """Most-mentioned tickers across tracked subreddits (cashtags + watchlist names)."""
    if settings.demo_mode:
        posts = [p for t in settings.watchlist for p in demo.social(t)]
    else:
        posts = await _safe("reddit", "reddit", settings.cache_ttl,
                            lambda: social.fetch_reddit(set(settings.watchlist)), [])
    agg: dict[str, list[float]] = {}
    for p in posts:
        agg.setdefault(p.ticker, []).append(p.sentiment)
    rows = [{"ticker": t, "mentions": len(v), "sentiment": round(sum(v) / len(v), 3)} for t, v in agg.items()]
    return sorted(rows, key=lambda r: r["mentions"], reverse=True)[:20]


async def get_fund_moves() -> list[FundMove]:
    if settings.demo_mode:
        return demo.fund_moves(settings.watchlist)
    # 13F data changes quarterly; refresh every 6 hours.
    return await _safe("sec_13f", "13f", 6 * 3600, portfolios.fetch_all, [])
