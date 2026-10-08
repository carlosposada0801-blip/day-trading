"""Optional Claude-based sentiment scoring for headlines and posts.

The lexicon misses sarcasm, context and relevance ("puts on SPY, long AAPL").
When AI_SENTIMENT=1, new texts are scored by Claude in one batched request per
ticker; results are cached in SQLite so each text is only ever billed once.
Any failure falls back silently to the lexicon scores already on the items.
"""
import hashlib
import json
import logging

import anthropic

from app import store
from app.config import settings
from app.models import Article, SocialPost

log = logging.getLogger(__name__)
MAX_ITEMS = 60

SYSTEM = """You score market sentiment for a day trader's research dashboard.

For each numbered item (a news headline or a social media post) about the given stock ticker,
return how it bears on that stock's near-term price, from -1 (clearly bearish) to 1 (clearly
bullish). Use 0 when the item is neutral, purely informational, or not really about this ticker.

Read it the way an experienced trader would: catch sarcasm and irony, retail-trader slang
("bagholder", "to the moon", "puts printing"), and cases where the text is bullish on a
different company. Headlines that only ask a question or list "things to watch" are usually
near 0. Reserve values beyond +/-0.7 for unambiguous, material news or strong conviction."""

SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"i": {"type": "integer"}, "sentiment": {"type": "number"}},
                "required": ["i", "sentiment"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scores"],
    "additionalProperties": False,
}

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


def _hash(ticker: str, text: str) -> str:
    return hashlib.sha256(f"{settings.ai_model}|{ticker}|{text}".encode()).hexdigest()


def _parse(text: str, n: int) -> dict[int, float]:
    out = {}
    for row in json.loads(text).get("scores", []):
        i = row.get("i")
        if isinstance(i, int) and 0 <= i < n:
            out[i] = max(-1.0, min(1.0, float(row["sentiment"])))
    return out


async def _score(ticker: str, texts: list[str]) -> dict[int, float] | None:
    listing = "\n".join(f"{i}. {t[:500]}" for i, t in enumerate(texts))
    try:
        resp = await _get_client().beta.messages.create(
            model=settings.ai_model,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"Ticker: {ticker}\n\nItems:\n{listing}"}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError:
        log.warning("AI sentiment rate limited; using lexicon")
        return None
    except anthropic.APIStatusError as e:
        log.warning("AI sentiment API error %s: %s", e.status_code, e.message)
        return None
    except anthropic.APIConnectionError as e:
        log.warning("AI sentiment connection error: %s", e)
        return None
    except TypeError as e:  # the SDK raises this when no API key / credentials are configured
        log.warning("AI sentiment unavailable (set ANTHROPIC_API_KEY): %s", e)
        return None
    if resp.stop_reason != "end_turn":
        log.warning("AI sentiment stopped with %s; using lexicon", resp.stop_reason)
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return _parse(text, len(texts))
    except (ValueError, KeyError, TypeError):
        log.warning("AI sentiment returned unparseable output")
        return None


async def rescore(ticker: str, articles: list[Article], posts: list[SocialPost]) -> bool:
    """Replace lexicon sentiment with Claude's where available. Returns True if Claude scored them."""
    items = [(a, a.title) for a in articles] + [(p, p.text) for p in posts if p.label is None]
    items = items[:MAX_ITEMS]
    if not items:
        return False
    hashes = [_hash(ticker, text) for _, text in items]
    cached = store.ai_cached(hashes)
    todo = [k for k, h in enumerate(hashes) if h not in cached]
    if todo:
        scored = await _score(ticker, [items[k][1] for k in todo])
        if scored is None:
            return False
        fresh = {hashes[k]: scored[j] for j, k in enumerate(todo) if j in scored}
        store.ai_store(fresh)
        cached.update(fresh)
    for (obj, _), h in zip(items, hashes):
        if h in cached:
            obj.sentiment = cached[h]
    return True
