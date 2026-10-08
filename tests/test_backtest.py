from app import backtest
from app.models import PriceInfo


def test_spearman():
    assert backtest.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1
    assert backtest.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1
    assert backtest.spearman([1, 2], [1, 2]) is None


def test_forward_return():
    p = PriceInfo(ticker="X", price=4, prev_close=3, closes=[1, 2, 3, 4],
                  dates=["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"])
    assert backtest.forward_return(p, "2026-01-02T15:00:00+00:00", 2) == 1.0
    assert backtest.forward_return(p, "2026-01-03", 1) == 4 / 3 - 1  # weekend snaps to next trading day
    assert backtest.forward_return(p, "2026-01-05", 5) is None


def test_evaluate_perfect_predictor():
    r = backtest.evaluate([(50, 0.02), (-50, -0.03), (60, 0.03), (-40, -0.01), (0, 0.0)])
    assert r["ic"] == 1.0 and r["hit_rate"] == 1.0 and r["calls"] == 4
    assert r["long_short_pct"] == 4.5


def test_track_record_uses_last_snapshot_per_day():
    p = PriceInfo(ticker="X", price=3, prev_close=2, closes=[1, 2, 3], dates=["2026-01-01", "2026-01-02", "2026-01-03"])
    hist = [{"ticker": "X", "ts": "2026-01-01T10:00", "score": -50},
            {"ticker": "X", "ts": "2026-01-01T15:00", "score": 50},
            {"ticker": "X", "ts": "2026-01-02T15:00", "score": 30}]
    r = backtest.track_record(hist, {"X": p}, 1)
    assert r["n"] == 2 and r["hit_rate"] == 1.0
