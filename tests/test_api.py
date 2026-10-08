from fastapi.testclient import TestClient

from app import auth
from app.main import app

client = TestClient(app)
client.post("/login", data={"password": "test-pass"})


def test_locked_without_login():
    anon = TestClient(app)
    assert anon.get("/api/signals").status_code == 401
    r = anon.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert anon.get("/docs", follow_redirects=False).status_code == 303
    assert anon.get("/login").status_code == 200


def test_wrong_password_and_lockout():
    anon = TestClient(app)
    for _ in range(auth.MAX_FAILS):
        r = anon.post("/login", data={"password": "nope"}, follow_redirects=False)
        assert "error=1" in r.headers["location"]
    r = anon.post("/login", data={"password": "test-pass"}, follow_redirects=False)
    assert "error=locked" in r.headers["location"]  # even the right password is refused while locked
    auth._fails.clear()


def test_forged_cookie_rejected():
    anon = TestClient(app)
    anon.cookies.set(auth.COOKIE, "9999999999.deadbeef")
    assert anon.get("/api/signals").status_code == 401
    good = auth.make_token()
    expired = "1." + good.split(".")[1]
    assert not auth.valid_token(expired)


def test_dashboard_served():
    r = client.get("/")
    assert r.status_code == 200 and "Signal Desk" in r.text


def test_signals_sorted_with_new_components():
    rows = client.get("/api/signals").json()
    assert rows and [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)
    assert {"insiders", "congress"} <= set(rows[0]["components"])


def test_ticker_detail_and_validation():
    d = client.get("/api/ticker/nvda").json()
    assert d["signal"]["ticker"] == "NVDA" and d["news"] and d["closes"]
    assert "insiders" in d and "congress" in d and "history" in d
    assert client.get("/api/ticker/<script>").status_code in (400, 404)


def test_alerts_and_backtest_endpoints():
    assert client.post("/api/alerts/run").status_code == 200
    assert "alerts" in client.get("/api/alerts").json()
    b = client.get("/api/backtest?horizon=5").json()
    assert b["momentum"]["n"] > 100 and b["snapshots"] > 0
    assert client.get("/api/backtest?horizon=0").status_code == 400


def test_paper_order_flow():
    client.post("/api/paper/reset")
    assert client.post("/api/paper/order", json={"ticker": "AAPL", "side": "buy", "qty": 5}).status_code == 200
    r = client.post("/api/paper/order", json={"ticker": "AAPL", "side": "sell", "qty": 50})
    assert r.status_code == 400 and "no shorting" in r.json()["detail"]
    p = client.get("/api/paper").json()
    assert p["positions"][0]["ticker"] == "AAPL" and len(p["trades"]) == 1
