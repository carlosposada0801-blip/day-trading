"""Paper trading: simulated orders against a SQLite ledger. No real money moves."""
import sqlite3
from datetime import datetime, timezone

from app.config import settings


class TradeError(ValueError):
    pass


class PaperAccount:
    def __init__(self, db_path: str | None = None, starting_cash: float | None = None):
        self.db = sqlite3.connect(db_path or settings.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.starting_cash = starting_cash if starting_cash is not None else settings.starting_cash
        self.db.execute("""CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY, ts TEXT, ticker TEXT, side TEXT, qty REAL, price REAL, note TEXT)""")
        # Simulated deposits (+) and withdrawals (-), so autopilot funding can be practiced.
        self.db.execute("CREATE TABLE IF NOT EXISTS cash_flows (id INTEGER PRIMARY KEY, ts TEXT, amount REAL)")
        self.db.commit()

    def trades(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM trades ORDER BY id DESC")]

    def contributed(self) -> float:
        """Starting cash plus net simulated deposits."""
        flows = self.db.execute("SELECT COALESCE(SUM(amount), 0) FROM cash_flows").fetchone()[0]
        return self.starting_cash + flows

    def transfer(self, amount: float) -> float:
        """Simulate a deposit (amount > 0) or withdrawal (amount < 0). Returns new cash."""
        cash, _ = self._state()
        if amount == 0:
            raise TradeError("amount must not be zero")
        if amount < 0 and -amount > cash + 1e-6:
            raise TradeError(f"can't withdraw ${-amount:,.2f}; only ${cash:,.2f} in cash")
        self.db.execute("INSERT INTO cash_flows (ts, amount) VALUES (?, ?)",
                        (datetime.now(timezone.utc).isoformat(), amount))
        self.db.commit()
        return round(cash + amount, 2)

    def _state(self) -> tuple[float, dict[str, dict]]:
        cash = self.contributed()
        pos: dict[str, dict] = {}
        for t in self.db.execute("SELECT * FROM trades ORDER BY id"):
            p = pos.setdefault(t["ticker"], {"qty": 0.0, "cost": 0.0, "realized": 0.0})
            if t["side"] == "buy":
                cash -= t["qty"] * t["price"]
                p["cost"] += t["qty"] * t["price"]
                p["qty"] += t["qty"]
            else:
                avg = p["cost"] / p["qty"]
                cash += t["qty"] * t["price"]
                p["realized"] += (t["price"] - avg) * t["qty"]
                p["cost"] -= avg * t["qty"]
                p["qty"] -= t["qty"]
        return cash, pos

    def summary(self, prices: dict[str, float]) -> dict:
        cash, pos = self._state()
        positions, mkt_value, realized = [], 0.0, 0.0
        for t, p in sorted(pos.items()):
            realized += p["realized"]
            if p["qty"] <= 1e-9:
                continue
            last = prices.get(t, p["cost"] / p["qty"])
            value = p["qty"] * last
            mkt_value += value
            positions.append({"ticker": t, "qty": p["qty"], "avg_cost": round(p["cost"] / p["qty"], 4),
                              "last": last, "value": round(value, 2),
                              "unrealized": round(value - p["cost"], 2)})
        equity = cash + mkt_value
        return {"cash": round(cash, 2), "equity": round(equity, 2), "positions": positions,
                "realized_pnl": round(realized, 2),
                "contributed": round(self.contributed(), 2),
                "total_pnl": round(equity - self.contributed(), 2),
                "total_pnl_pct": round((equity / self.contributed() - 1) * 100, 2) if self.contributed() else 0.0}

    def order(self, ticker: str, side: str, qty: float, price: float,
              prices: dict[str, float], note: str = "", enforce_limit: bool = True) -> dict:
        ticker = ticker.upper()
        if side not in ("buy", "sell"):
            raise TradeError("side must be 'buy' or 'sell'")
        if qty <= 0 or price <= 0:
            raise TradeError("quantity and price must be positive")
        cash, pos = self._state()
        held = pos.get(ticker, {}).get("qty", 0.0)
        if side == "buy":
            if qty * price > cash + 1e-6:
                raise TradeError(f"insufficient cash: need ${qty * price:,.2f}, have ${cash:,.2f}")
            equity = self.summary({**prices, ticker: price})["equity"]
            # Manual paper trades get this guardrail; the autotrader applies its own limits instead.
            if enforce_limit and (held + qty) * price > settings.max_position_pct * equity:
                raise TradeError(f"position would exceed {settings.max_position_pct:.0%} of equity "
                                 f"(risk limit, set MAX_POSITION_PCT to change)")
        elif qty > held + 1e-9:
            raise TradeError(f"cannot sell {qty} {ticker}: only {held} held (no shorting)")
        cur = self.db.execute(
            "INSERT INTO trades (ts, ticker, side, qty, price, note) VALUES (?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), ticker, side, qty, price, note))
        self.db.commit()
        return {"id": cur.lastrowid, "ticker": ticker, "side": side, "qty": qty, "price": price}

    def reset(self) -> None:
        self.db.execute("DELETE FROM trades")
        self.db.execute("DELETE FROM cash_flows")
        self.db.commit()
