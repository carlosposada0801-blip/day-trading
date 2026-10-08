"""SQLite storage for score history, alerts and the AI sentiment cache."""
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from app.config import settings

_lock = threading.Lock()
_db: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = sqlite3.connect(settings.db_path, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.executescript("""
            CREATE TABLE IF NOT EXISTS score_history (
                ts TEXT, ticker TEXT, score REAL, stance TEXT, price REAL, components TEXT);
            CREATE INDEX IF NOT EXISTS ix_hist ON score_history (ticker, ts);
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY, ts TEXT, ticker TEXT, kind TEXT, message TEXT,
                score REAL, prev_score REAL, seen INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS ai_cache (hash TEXT PRIMARY KEY, sentiment REAL, ts TEXT);
        """)
    return _db


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_score(ticker: str, score: float, stance: str, price: float | None, components: str,
                 ts: str | None = None) -> None:
    with _lock:
        db().execute("INSERT INTO score_history VALUES (?,?,?,?,?,?)",
                     (ts or now(), ticker, score, stance, price, components))
        db().commit()


def history(ticker: str | None = None, since_hours: float | None = None) -> list[dict]:
    q, args = "SELECT * FROM score_history WHERE 1=1", []
    if ticker:
        q += " AND ticker = ?"
        args.append(ticker)
    if since_hours is not None:
        q += " AND ts >= ?"
        args.append((datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat())
    return [dict(r) for r in db().execute(q + " ORDER BY ts", args)]


def add_alert(ticker: str, kind: str, message: str, score: float, prev_score: float | None) -> dict:
    with _lock:
        cur = db().execute("INSERT INTO alerts (ts, ticker, kind, message, score, prev_score) VALUES (?,?,?,?,?,?)",
                           (now(), ticker, kind, message, score, prev_score))
        db().commit()
    return dict(db().execute("SELECT * FROM alerts WHERE id = ?", (cur.lastrowid,)).fetchone())


def alerts(limit: int = 50) -> list[dict]:
    return [dict(r) for r in db().execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]


def last_alert(ticker: str) -> dict | None:
    r = db().execute("SELECT * FROM alerts WHERE ticker = ? ORDER BY id DESC LIMIT 1", (ticker,)).fetchone()
    return dict(r) if r else None


def mark_alerts_seen() -> None:
    with _lock:
        db().execute("UPDATE alerts SET seen = 1 WHERE seen = 0")
        db().commit()


def ai_cached(hashes: list[str]) -> dict[str, float]:
    if not hashes:
        return {}
    marks = ",".join("?" * len(hashes))
    return {r["hash"]: r["sentiment"] for r in db().execute(
        f"SELECT hash, sentiment FROM ai_cache WHERE hash IN ({marks})", hashes)}


def ai_store(values: dict[str, float]) -> None:
    with _lock:
        db().executemany("INSERT OR REPLACE INTO ai_cache VALUES (?,?,?)",
                         [(h, s, now()) for h, s in values.items()])
        db().commit()
