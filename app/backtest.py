"""Does the score actually predict anything? Measure it before trusting it.

Two views:
  * track record: every score snapshot the app recorded vs. the stock's return over the
    next N trading days. This is the honest test of the full blended score, and it grows
    as the app runs (news/social history can't be fetched retroactively for free).
  * momentum: the price-only component replayed over a year of daily data, available now.

Metrics: information coefficient (rank correlation of score vs forward return), hit rate
(direction right when the stance was bullish/bearish), and the average forward return per
stance. Ignores trading costs and slippage, so real results would be worse.
"""
import math
from bisect import bisect_left

from app.models import PriceInfo


def forward_return(price: PriceInfo, day: str, horizon: int) -> float | None:
    i = bisect_left(price.dates, day[:10])
    if i >= len(price.closes) or i + horizon >= len(price.closes):
        return None
    return price.closes[i + horizon] / price.closes[i] - 1


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return cov / var if var else None


def evaluate(samples: list[tuple[float, float]], threshold: float = 20) -> dict:
    """samples: (score, forward_return) pairs."""
    if not samples:
        return {"n": 0}
    scores, rets = [s for s, _ in samples], [r for _, r in samples]
    buckets = {"bullish": [], "neutral": [], "bearish": []}
    hits = calls = 0
    for s, r in samples:
        stance = "bullish" if s > threshold else "bearish" if s < -threshold else "neutral"
        buckets[stance].append(r)
        if stance != "neutral":
            calls += 1
            hits += (r > 0) == (stance == "bullish")
    avg = {k: (round(sum(v) / len(v) * 100, 3) if v else None) for k, v in buckets.items()}
    ic = spearman(scores, rets)
    return {
        "n": len(samples),
        "ic": round(ic, 3) if ic is not None else None,
        "hit_rate": round(hits / calls, 3) if calls else None,
        "calls": calls,
        "avg_fwd_return_pct": avg,
        "counts": {k: len(v) for k, v in buckets.items()},
        "long_short_pct": (round(avg["bullish"] - avg["bearish"], 3)
                           if avg["bullish"] is not None and avg["bearish"] is not None else None),
    }


def track_record(history: list[dict], prices: dict[str, PriceInfo], horizon: int) -> dict:
    """Use the last snapshot per ticker per day so frequent polling doesn't overweight a day."""
    daily: dict[tuple[str, str], float] = {}
    for row in history:
        daily[(row["ticker"], row["ts"][:10])] = row["score"]
    samples = []
    for (ticker, day), score in daily.items():
        p = prices.get(ticker)
        r = forward_return(p, day, horizon) if p else None
        if r is not None:
            samples.append((score, r))
    return evaluate(samples)


def momentum_backtest(price: PriceInfo, horizon: int) -> list[tuple[float, float]]:
    out = []
    c = price.closes
    for t in range(5, len(c) - horizon):
        score = 100 * math.tanh((c[t] / c[t - 5] - 1) / 0.05)
        out.append((score, c[t + horizon] / c[t] - 1))
    return out
