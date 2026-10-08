"""Every trading decision, approval request and switch, stored in SQLite."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone

from app import store

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY, ts TEXT, broker TEXT, mode TEXT, ticker TEXT, side TEXT, qty REAL,
    price REAL, limit_price REAL, score REAL, reasons TEXT, status TEXT, detail TEXT, order_id TEXT,
    fill_price REAL);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY, ts TEXT, expires TEXT, decision_id INTEGER, status TEXT);
"""
_ready = False


def _db():
    global _ready
    db = store.db()
    if not _ready:
        db.executescript(_SCHEMA)
        _ready = True
    return db


def now() -> datetime:
    return datetime.now(timezone.utc)


def get(key: str, default=None):
    r = _db().execute("SELECT value FROM trade_state WHERE key = ?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def put(key: str, value) -> None:
    with store._lock:
        _db().execute("INSERT OR REPLACE INTO trade_state VALUES (?, ?)", (key, json.dumps(value)))
        _db().commit()


def log(*, broker: str, mode: str, ticker: str, side: str, qty: float, price: float | None,
        limit_price: float | None, score: float | None, reasons: list[str], status: str, detail: str = "",
        order_id: str | None = None, fill_price: float | None = None) -> int:
    with store._lock:
        cur = _db().execute(
            "INSERT INTO decisions (ts, broker, mode, ticker, side, qty, price, limit_price, score, reasons, status,"
            " detail, order_id, fill_price) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now().isoformat(), broker, mode, ticker, side, qty, price, limit_price, score,
             json.dumps(reasons), status, detail, order_id, fill_price))
        _db().commit()
    return cur.lastrowid


def update(decision_id: int, **fields) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    with store._lock:
        _db().execute(f"UPDATE decisions SET {sets} WHERE id = ?", (*fields.values(), decision_id))
        _db().commit()


def decision(decision_id: int) -> dict | None:
    r = _db().execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    return _row(r) if r else None


def _row(r) -> dict:
    d = dict(r)
    d["reasons"] = json.loads(d["reasons"] or "[]")
    return d


def decisions(limit: int = 100) -> list[dict]:
    return [_row(r) for r in _db().execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))]


def executed_since(since: datetime) -> list[dict]:
    """Orders sent to the broker. Submitted-but-unconfirmed orders count too, so limits err on the safe side."""
    return [_row(r) for r in _db().execute(
        "SELECT * FROM decisions WHERE status IN ('filled', 'submitted') AND ts >= ? ORDER BY id",
        (since.isoformat(),))]


def submitted_today(day_start: datetime) -> int:
    return _db().execute("SELECT COUNT(*) FROM decisions WHERE status IN ('filled', 'submitted') AND ts >= ?",
                         (day_start.isoformat(),)).fetchone()[0]


def add_proposal(decision_id: int, ttl_min: int) -> int:
    with store._lock:
        cur = _db().execute("INSERT INTO proposals (ts, expires, decision_id, status) VALUES (?,?,?, 'pending')",
                            (now().isoformat(), (now() + timedelta(minutes=ttl_min)).isoformat(), decision_id))
        _db().commit()
    return cur.lastrowid


def proposals(status: str | None = "pending") -> list[dict]:
    q = "SELECT p.id AS proposal_id, p.expires, p.status AS proposal_status, d.* FROM proposals p " \
        "JOIN decisions d ON d.id = p.decision_id"
    args = ()
    if status:
        q += " WHERE p.status = ?"
        args = (status,)
    return [_row(r) for r in _db().execute(q + " ORDER BY p.id DESC LIMIT 50", args)]


def set_proposal(proposal_id: int, status: str) -> None:
    with store._lock:
        _db().execute("UPDATE proposals SET status = ? WHERE id = ?", (status, proposal_id))
        _db().commit()


def expire_proposals() -> int:
    stale = [p for p in proposals("pending") if p["expires"] < now().isoformat()]
    for p in stale:
        set_proposal(p["proposal_id"], "expired")
        update(p["id"], status="expired")
    return len(stale)


def csv_export() -> str:
    rows = decisions(100_000)
    buf = io.StringIO()
    cols = ["id", "ts", "broker", "mode", "ticker", "side", "qty", "price", "limit_price", "fill_price",
            "score", "status", "reasons", "detail", "order_id"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in reversed(rows):
        w.writerow({**r, "reasons": "; ".join(r["reasons"])})
    return buf.getvalue()
