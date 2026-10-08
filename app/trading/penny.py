"""Penny stocks: their own small sleeve with stricter rules.

Penny stocks move a lot, trade thinly, and are the favourite target of pump-and-dump
schemes run through exactly the kind of social media this app reads. So:
  * only exchange-listed stocks (no OTC / pink sheets), between min_price and max_price
  * enough daily dollar volume that you can actually get out
  * a pump guard: a big run-up on social hype with no supporting news is refused
  * a separate budget and position count, wider stops, shorter holds
"""
import asyncio
import copy

from app import data, engine
from app.models import PriceInfo, Signal
from app.trading import journal
from app.trading.strategy import Strategy

HELD_KEY = "penny_held"


def eligibility(cfg: Strategy, p: PriceInfo | None) -> list[str]:
    """Reasons this stock can't be a penny buy. Empty list = eligible."""
    c = cfg.penny
    if p is None:
        return ["no price data"]
    out = []
    if p.is_otc:
        out.append(f"over-the-counter ({p.exchange}): not exchange-listed")
    if p.price < c.min_price:
        out.append(f"price ${p.price:.4f} under ${c.min_price:.2f} minimum")
    if p.price > c.max_price:
        out.append(f"price ${p.price:.2f} over ${c.max_price:.2f} (not a penny stock)")
    dv = p.avg_dollar_volume()
    if dv is None:
        out.append("no volume data; can't check liquidity")
    elif dv < c.min_dollar_volume:
        out.append(f"only ${dv:,.0f}/day traded (min ${c.min_dollar_volume:,.0f}): hard to sell")
    return out


def pump_flags(cfg: Strategy, p: PriceInfo, sig: Signal) -> list[str]:
    """Warning signs of a pump-and-dump."""
    if not cfg.penny.pump_guard or len(p.closes) < 6:
        return []
    run_up = p.closes[-1] / p.closes[-6] - 1
    social = sig.components.get("social")
    news = sig.components.get("news")
    hype = (social is not None and social >= 0.3) or sig.counts.get("social", 0) >= 10
    no_news = news is None or news < 0.2
    flags = []
    if run_up >= cfg.penny.pump_run_up_pct / 100 and hype and no_news:
        flags.append(f"possible pump: +{run_up:.0%} in 5 days on social hype without supporting news")
    if len(p.volumes) >= 20:
        recent = sum(p.volumes[-5:]) / 5
        before = sum(p.volumes[-20:-5]) / 15 or 1
        if recent / before >= 5 and run_up >= 0.3:
            flags.append(f"volume {recent / before:.0f}x normal with +{run_up:.0%} run-up")
    return flags


def exit_cfg(cfg: Strategy) -> Strategy:
    """A copy of the strategy whose exit rules are the penny ones."""
    c = copy.deepcopy(cfg)
    c.exit.stop_loss_pct = cfg.penny.stop_loss_pct
    c.exit.take_profit_pct = cfg.penny.take_profit_pct
    c.exit.max_hold_days = cfg.penny.max_hold_days
    return c


def held() -> set[str]:
    return set(journal.get(HELD_KEY, []))


def mark_held(ticker: str, is_held: bool) -> None:
    s = held()
    (s.add if is_held else s.discard)(ticker)
    journal.put(HELD_KEY, sorted(s))


async def scan(cfg: Strategy, exclude: set[str] = frozenset()) -> list[dict]:
    """Score every penny candidate and say whether it's buyable and why not."""
    if not cfg.penny.enabled:
        return []
    tickers = [t.upper() for t in cfg.penny.watchlist]
    if cfg.penny.scan_trending:
        tickers += [r["ticker"] for r in await data.get_trending()]
    tickers = [t for t in dict.fromkeys(tickers) if t not in exclude]
    prices = await asyncio.gather(*(data.get_price(t) for t in tickers))
    in_range = [(t, p) for t, p in zip(tickers, prices)
                if p and p.price <= cfg.penny.max_price * 1.5]  # skip obvious non-pennies early
    results = await asyncio.gather(*(engine.compute(t) for t, _ in in_range))
    rows = []
    for (t, p), r in zip(in_range, results):
        sig = r["signal"]
        blocks = eligibility(cfg, p)
        flags = pump_flags(cfg, p, sig)
        if sig.score < cfg.penny.min_score:
            blocks.append(f"score {sig.score:+.0f} under {cfg.penny.min_score:.0f}")
        if sig.confidence < cfg.penny.min_confidence:
            blocks.append(f"confidence {sig.confidence:.0%} under {cfg.penny.min_confidence:.0%}")
        rows.append({"ticker": t, "price": p.price, "exchange": p.exchange,
                     "dollar_volume": p.avg_dollar_volume(), "signal": sig,
                     "blocks": blocks + flags, "pump": bool(flags), "eligible": not blocks and not flags})
    return sorted(rows, key=lambda r: (not r["eligible"], -r["signal"].score))
