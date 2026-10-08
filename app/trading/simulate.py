"""Replay the strategy's actual buy/sell rules over daily history, with costs, vs. holding SPY.

Scores come from either the price-momentum component (a year of history available now) or
the full blended scores the app has recorded. Confidence isn't stored historically, so the
entry confidence filter is skipped here.
"""
import math

from app.models import PriceInfo
from app.trading import strategy


def momentum_scores(price: PriceInfo) -> dict[str, float]:
    c = price.closes
    return {price.dates[t]: 100 * math.tanh((c[t] / c[t - 5] - 1) / 0.05) for t in range(5, len(c))}


def recorded_scores(history: list[dict]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in history:
        out.setdefault(row["ticker"], {})[row["ts"][:10]] = row["score"]
    return out


def run(scores: dict[str, dict[str, float]], prices: dict[str, PriceInfo], cfg: strategy.Strategy,
        benchmark: PriceInfo | None = None, cost_bps: float = 10, start_cash: float = 100_000) -> dict:
    px = {t: dict(zip(p.dates, p.closes)) for t, p in prices.items()}
    days = sorted({d for t in scores for d in scores[t] if d in px.get(t, {})})
    if len(days) < 2:
        return {"days": len(days)}
    cost = cost_bps / 10_000
    cash, holdings = start_cash, {}  # ticker -> (qty, cost_per_share, entry_index)
    last_px: dict[str, float] = {}
    trades, curve = [], []
    for k, d in enumerate(days):
        for t in px:
            if d in px[t]:
                last_px[t] = px[t][d]
        for t, (qty, basis, entered) in list(holdings.items()):
            p = last_px.get(t)
            if p is None:
                continue
            why = strategy.exit_reason(cfg, basis, p, scores.get(t, {}).get(d), k - entered)
            if why:
                cash += qty * p * (1 - cost)
                trades.append((p * (1 - cost)) / basis - 1)
                del holdings[t]
        equity = cash + sum(q * last_px.get(t, b) for t, (q, b, _) in holdings.items())
        ranked = sorted(((s[d], t) for t, s in scores.items() if d in s and t in last_px and t not in holdings),
                        reverse=True)
        for score, t in ranked:
            if score < cfg.entry.min_score or len(holdings) >= cfg.sizing.max_positions:
                break
            p = last_px[t] * (1 + cost)
            qty = strategy.position_qty(cfg, equity, p)
            if qty and qty * p <= cash and qty * p <= equity * cfg.risk.max_position_pct / 100:
                cash -= qty * p
                holdings[t] = (qty, p, k)
        curve.append(cash + sum(q * last_px.get(t, b) for t, (q, b, _) in holdings.items()))
    peak, max_dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1)
    result = {
        "days": len(days), "from": days[0], "to": days[-1],
        "total_return_pct": round((curve[-1] / start_cash - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "trades": len(trades),
        "win_rate": round(sum(1 for r in trades if r > 0) / len(trades), 3) if trades else None,
        "avg_trade_pct": round(sum(trades) / len(trades) * 100, 2) if trades else None,
        "cost_bps_per_side": cost_bps,
        "open_positions": len(holdings),
        "curve": [round(v, 2) for v in curve],
        "dates": days,
    }
    if benchmark:
        b = dict(zip(benchmark.dates, benchmark.closes))
        span = [b[d] for d in days if d in b]
        if len(span) >= 2:
            result["benchmark_return_pct"] = round((span[-1] / span[0] - 1) * 100, 2)
            result["beats_benchmark"] = result["total_return_pct"] > result["benchmark_return_pct"]
    return result
