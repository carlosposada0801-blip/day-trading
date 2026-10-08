"""Trading rules, loaded from strategy.toml. Pure functions so they can be backtested."""
import math
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from app.config import settings


@dataclass
class Entry:
    min_score: float = 40
    min_confidence: float = 0.6
    min_components: dict = field(default_factory=dict)


@dataclass
class Exit:
    stop_loss_pct: float = 8
    take_profit_pct: float = 15
    exit_score_below: float = 0
    max_hold_days: int = 20
    close_at_eod: bool = False


@dataclass
class Sizing:
    position_pct: float = 10
    max_positions: int = 5


@dataclass
class Risk:
    daily_loss_limit_pct: float = 3
    max_trades_per_day: int = 6
    max_order_usd: float = 2000
    max_position_pct: float = 20
    max_failed_sources: int = 1
    max_day_trades_per_5d: int = 3
    avoid_wash_sales: bool = True
    no_trade_open_minutes: int = 15
    no_trade_close_minutes: int = 15
    limit_band_pct: float = 0.5


@dataclass
class Schedule:
    interval_min: int = 5
    proposal_ttl_min: int = 15


@dataclass
class Autopilot:
    core_symbol: str = "VOO"          # broad index fund that holds most of the money
    core_pct: float = 60              # % of investable equity kept in the core fund (0 = none)
    cash_reserve_pct: float = 5       # % of equity always left in cash
    rebalance_band_pct: float = 5     # only rebalance the core when it's this far off target
    core_max_order_usd: float = 5000  # new deposits are invested in steps of at most this
    profit_pull_trigger_pct: float = 10  # set profits aside once you're up this % on what you put in
    profit_pull_share_pct: float = 50    # ...and set aside this share of the profit
    min_pull_usd: float = 50          # ignore smaller amounts
    weekly_summary: bool = True       # push a summary after Friday's close


@dataclass
class RobinhoodCfg:
    mcp_url: str = "https://agent.robinhood.com/mcp/trading"
    tools: dict = field(default_factory=dict)
    order_args: dict = field(default_factory=dict)


@dataclass
class Strategy:
    entry: Entry = field(default_factory=Entry)
    exit: Exit = field(default_factory=Exit)
    sizing: Sizing = field(default_factory=Sizing)
    risk: Risk = field(default_factory=Risk)
    schedule: Schedule = field(default_factory=Schedule)
    autopilot: Autopilot = field(default_factory=Autopilot)
    robinhood: RobinhoodCfg = field(default_factory=RobinhoodCfg)


def load(path: str | None = None) -> Strategy:
    p = Path(path or settings.strategy_path)
    raw = tomllib.loads(p.read_text()) if p.is_file() else {}
    s = Strategy()
    for f in fields(s):
        section, values = getattr(s, f.name), raw.get(f.name, {})
        known = {x.name for x in fields(section)}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"strategy.toml [{f.name}]: unknown setting(s) {sorted(unknown)}")
        for k, v in values.items():
            setattr(section, k, v)
    return s


def entry_reasons(cfg: Strategy, sig) -> list[str] | None:
    """Why this signal qualifies for a buy, or None if it doesn't."""
    e = cfg.entry
    if sig.price is None or sig.score < e.min_score or sig.confidence < e.min_confidence:
        return None
    for comp, minimum in e.min_components.items():
        v = sig.components.get(comp)
        if v is None or v < minimum:
            return None
    top = sorted(((k, v) for k, v in sig.components.items() if v is not None), key=lambda kv: -kv[1])[:3]
    return [f"score {sig.score:+.0f} (conf {sig.confidence:.0%})"] + [f"{k} {v:+.2f}" for k, v in top]


def exit_reason(cfg: Strategy, avg_cost: float, price: float, score: float | None, held_days: float) -> str | None:
    x = cfg.exit
    change = (price / avg_cost - 1) * 100 if avg_cost else 0
    if change <= -x.stop_loss_pct:
        return f"stop-loss: {change:+.1f}%"
    if change >= x.take_profit_pct:
        return f"take-profit: {change:+.1f}%"
    if score is not None and score < x.exit_score_below:
        return f"score fell to {score:+.0f}"
    if held_days >= x.max_hold_days:
        return f"held {held_days:.0f} days"
    return None


def position_qty(cfg: Strategy, equity: float, price: float) -> int:
    budget = min(equity * cfg.sizing.position_pct / 100, cfg.risk.max_order_usd)
    return max(0, math.floor(budget / price)) if price > 0 else 0
