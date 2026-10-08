"""Hands-off money management on top of the autotrader.

* Funding: each cycle compares the account's cash with what our own orders explain. A jump
  up is a deposit, a drop is a withdrawal. That gives "net deposits", which is what your
  profit is measured against.
* Core: most of the money sits in one broad index fund (core_symbol), rebalanced only when it
  drifts past the band. New deposits get invested in steps.
* Satellite: the signal strategy trades what's left, within its own budget.
* Profit pulls: once you're up profit_pull_trigger_pct on net deposits, profit_pull_share_pct of
  the profit is set aside as cash (never reinvested) and you're told to withdraw it. Moving
  money to your bank stays a manual step in the Robinhood app.
"""
import math
from dataclasses import dataclass

from app.trading import calendar, journal
from app.trading.strategy import Strategy


@dataclass
class Funds:
    net_deposits: float
    reserved: float        # profit set aside for you to withdraw
    set_aside_total: float  # all profit ever set aside (reserved now + already withdrawn)
    events: list[tuple[str, float]]

    def profit(self, equity: float) -> float:
        return equity - self.net_deposits


def _key(broker: str, name: str) -> str:
    return f"ap:{broker}:{name}"


def load(broker: str) -> Funds | None:
    nd = journal.get(_key(broker, "net_deposits"))
    if nd is None:
        return None
    return Funds(nd, journal.get(_key(broker, "reserved"), 0.0), journal.get(_key(broker, "set_aside_total"), 0.0), [])


def _save(broker: str, f: Funds, cash: float, ts: str) -> None:
    journal.put(_key(broker, "net_deposits"), round(f.net_deposits, 2))
    journal.put(_key(broker, "reserved"), round(f.reserved, 2))
    journal.put(_key(broker, "set_aside_total"), round(f.set_aside_total, 2))
    journal.put(_key(broker, "last_cash"), round(cash, 2))
    journal.put(_key(broker, "last_ts"), ts)


def order_cash(rows: list[dict]) -> float:
    """Net cash our own orders moved: sells add, buys subtract."""
    total = 0.0
    for r in rows:
        px = r.get("fill_price") or r.get("limit_price") or r.get("price") or 0
        total += (1 if r["side"] == "sell" else -1) * r["qty"] * px
    return total


def update_funding(broker: str, equity: float, cash: float, orders_since_last: list[dict], now_iso: str,
                   known_net_deposits: float | None = None) -> Funds:
    """known_net_deposits: exact figure when the broker can tell us (practice account)."""
    f = load(broker)
    if f is None:  # first run: whatever is in the account counts as deposited
        f = Funds(known_net_deposits if known_net_deposits is not None else equity, 0.0, 0.0, [("start", equity)])
        _save(broker, f, cash, now_iso)
        return f
    if known_net_deposits is not None:
        diff, tolerance = known_net_deposits - f.net_deposits, 0.005
    else:
        expected = journal.get(_key(broker, "last_cash"), cash) + order_cash(orders_since_last)
        diff = cash - expected
        tolerance = max(25.0, 0.005 * equity)  # rounding, fees, small interest
        # A real deposit or withdrawal moves total equity too. An unfilled limit order that expired
        # hands its cash back without changing equity, so it must not count as a deposit.
        last_equity = journal.get(_key(broker, "last_equity"))
        if last_equity is not None and abs(diff) > tolerance and abs(equity - last_equity) < abs(diff) * 0.5:
            diff = 0.0
    journal.put(_key(broker, "last_equity"), round(equity, 2))
    if diff > tolerance:
        f.net_deposits += diff
        f.events.append(("deposit", diff))
    elif diff < -tolerance:
        f.net_deposits += diff
        f.reserved = max(0.0, f.reserved + diff)
        f.events.append(("withdrawal", -diff))
    _save(broker, f, cash, now_iso)
    return f


def maybe_pull(cfg: Strategy, f: Funds, equity: float, broker: str, cash: float, now_iso: str) -> float:
    """Set more profit aside if the trigger is met. Returns the newly reserved amount."""
    a = cfg.autopilot
    profit = f.profit(equity)
    if f.net_deposits <= 0 or profit < f.net_deposits * a.profit_pull_trigger_pct / 100:
        return 0.0
    eligible = profit * a.profit_pull_share_pct / 100 - f.set_aside_total
    if eligible < a.min_pull_usd:
        return 0.0
    f.reserved += eligible
    f.set_aside_total += eligible
    f.events.append(("pull", eligible))
    _save(broker, f, cash, now_iso)
    return eligible


def release(broker: str) -> float:
    """You decided to keep the set-aside profit invested."""
    f = load(broker)
    if not f:
        return 0.0
    amount = f.reserved
    f.reserved = 0.0
    _save(broker, f, journal.get(_key(broker, "last_cash"), 0.0), journal.get(_key(broker, "last_ts"), ""))
    return amount


def reserve_cash(cfg: Strategy, equity: float) -> float:
    return equity * cfg.autopilot.cash_reserve_pct / 100


def spendable(cfg: Strategy, equity: float, cash: float, reserved: float) -> float:
    return max(0.0, cash - reserved - reserve_cash(cfg, equity))


def core_order(cfg: Strategy, equity: float, reserved: float, spend: float, held_qty: float,
               price: float) -> tuple[str, int, str] | None:
    """('buy'|'sell', qty, reason) to move the core fund toward its target, or None."""
    a = cfg.autopilot
    if a.core_pct <= 0 or price <= 0:
        return None
    investable = max(0.0, equity - reserved)
    target = investable * a.core_pct / 100
    current = held_qty * price
    gap = target - current
    if abs(gap) <= equity * a.rebalance_band_pct / 100:
        return None
    if gap > 0:
        qty = math.floor(min(gap, a.core_max_order_usd, spend) / price)
        why = f"core {current / investable:.0%} of target {a.core_pct:.0f}%" if investable else "core"
        return ("buy", qty, f"invest in {a.core_symbol}: {why}") if qty > 0 else None
    qty = min(int(held_qty), math.floor(min(-gap, a.core_max_order_usd) / price))
    return ("sell", qty, f"rebalance {a.core_symbol}: above {a.core_pct:.0f}% target") if qty > 0 else None


def satellite_room(cfg: Strategy, equity: float, reserved: float, satellite_value: float) -> float:
    a = cfg.autopilot
    cap = max(0.0, equity - reserved) * max(0.0, 100 - a.core_pct - a.cash_reserve_pct) / 100
    return max(0.0, cap - satellite_value)


def cash_shortfall(cfg: Strategy, equity: float, cash: float, reserved: float) -> float:
    """Cash still needed to cover the money set aside for withdrawal."""
    return max(0.0, reserved - cash)


def weekly_summary_due(now) -> str | None:
    """ISO week label if it's after Friday's close and that week's summary hasn't gone out."""
    et = now.astimezone(calendar.ET)
    if et.weekday() != 4 or et.hour < 16 or (et.hour == 16 and et.minute < 5):
        return None
    week = f"{et.isocalendar().year}-W{et.isocalendar().week:02d}"
    return None if journal.get("ap:summary_week") == week else week
