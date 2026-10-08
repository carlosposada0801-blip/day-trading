import asyncio
from datetime import datetime, timedelta, timezone

from app import alerts, store


def _row(score, stance, hours_ago=1):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return {"ts": ts, "score": score, "stance": stance}


def test_big_move_fires():
    fired = alerts.evaluate("AAPL", 40, "bullish", [_row(5, "neutral", 6), _row(30, "bullish")])
    kinds = [k for k, _ in fired]
    assert "move" in kinds and "jumped" in fired[0][1]


def test_flip_fires_but_not_to_neutral():
    assert [k for k, _ in alerts.evaluate("X", -25, "bearish", [_row(-10, "neutral")])] == ["flip"]
    assert alerts.evaluate("X", 10, "neutral", [_row(21, "bullish")]) == []


def test_no_history_no_alert():
    assert alerts.evaluate("X", 90, "bullish", []) == []


def test_run_cycle_records_snapshots():
    before = len(store.history())
    asyncio.run(alerts.run_cycle())
    assert len(store.history()) > before
