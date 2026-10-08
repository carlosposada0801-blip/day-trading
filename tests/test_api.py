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


def test_trading_endpoints():
    s = client.get("/api/trading").json()
    assert {"mode", "broker", "proposals", "decisions", "robinhood", "rules"} <= set(s)
    assert client.post("/api/trading/mode", json={"mode": "approve", "broker": "sim"}).json()["mode"] == "approve"
    r = client.post("/api/trading/mode", json={"mode": "auto", "broker": "robinhood"})
    assert r.status_code == 400 and "ALLOW_LIVE_AUTO" in r.json()["detail"]
    run = client.post("/api/trading/run").json()  # demo mode ignores market hours
    assert "actions" in run
    pending = client.get("/api/trading").json()["proposals"]
    if pending:
        assert client.post(f"/api/trading/proposals/{pending[0]['proposal_id']}/reject").status_code == 200
    assert client.post("/api/trading/kill").json()["kill_switch"] is True
    assert client.post("/api/trading/resume").json()["kill_switch"] is False
    csv = client.get("/api/trading/journal.csv")
    assert csv.status_code == 200 and csv.text.startswith("id,ts,")
    bt = client.get("/api/trading/backtest?source=momentum").json()
    assert bt["days"] > 100 and "benchmark_return_pct" in bt


def test_robinhood_callback_is_public_but_inert():
    anon = TestClient(app)
    assert anon.get("/broker/robinhood/callback?code=x&state=y").status_code == 400


def test_edit_watchlist():
    from app.config import settings
    original = list(settings.watchlist)
    r = client.put("/api/watchlist", json={"tickers": ["aapl", "PLTR", "aapl", " "]})
    assert r.json()["watchlist"] == ["AAPL", "PLTR"]
    assert [s["ticker"] for s in client.get("/api/signals").json()] in (["AAPL", "PLTR"], ["PLTR", "AAPL"])
    assert client.put("/api/watchlist", json={"tickers": ["<x>"]}).status_code == 400
    assert client.put("/api/watchlist", json={"tickers": []}).status_code == 422
    client.put("/api/watchlist", json={"tickers": original})


def test_autopilot_endpoints():
    client.post("/api/trading/mode", json={"mode": "off", "broker": "sim"})
    s = client.get("/api/autopilot").json()
    assert {"running", "checks", "ready", "plan", "allocation"} <= set(s)
    assert s["broker"] == "sim" and s["plan"]["core_symbol"] == "VOO"
    assert client.post("/api/paper/transfer", json={"amount": 2500}).status_code == 200
    assert client.post("/api/paper/transfer", json={"amount": -10_000_000}).status_code == 400
    if s["ready"]:
        assert client.post("/api/autopilot/start").json()["running"] is True
        assert client.post("/api/autopilot/stop").json()["running"] is False
    assert "released" in client.post("/api/autopilot/release").json()


def test_autopilot_start_blocked_for_live_without_opt_in():
    client.post("/api/trading/mode", json={"mode": "off", "broker": "robinhood"})
    r = client.post("/api/autopilot/start")
    assert r.status_code == 400 and "Can't start autopilot" in r.json()["detail"]
    client.post("/api/trading/mode", json={"mode": "off", "broker": "sim"})
