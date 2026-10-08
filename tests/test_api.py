from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dashboard_served():
    r = client.get("/")
    assert r.status_code == 200 and "Signal Desk" in r.text


def test_signals_sorted_by_score():
    rows = client.get("/api/signals").json()
    assert rows and [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)


def test_ticker_detail_and_validation():
    d = client.get("/api/ticker/nvda").json()
    assert d["signal"]["ticker"] == "NVDA" and d["news"] and d["closes"]
    assert client.get("/api/ticker/<script>").status_code in (400, 404)


def test_paper_order_flow():
    client.post("/api/paper/reset")
    assert client.post("/api/paper/order", json={"ticker": "AAPL", "side": "buy", "qty": 5}).status_code == 200
    r = client.post("/api/paper/order", json={"ticker": "AAPL", "side": "sell", "qty": 50})
    assert r.status_code == 400 and "no shorting" in r.json()["detail"]
    p = client.get("/api/paper").json()
    assert p["positions"][0]["ticker"] == "AAPL" and len(p["trades"]) == 1
