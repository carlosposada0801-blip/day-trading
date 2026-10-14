import base64

from fastapi.testclient import TestClient

from app import auth, totp
from app.config import settings
from app.instance_lock import InstanceLock
from app.main import app

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


def test_totp_matches_rfc6238_vectors():
    assert totp.code_at(RFC_SECRET, 59 // 30, 8) == "94287082"
    assert totp.code_at(RFC_SECRET, 1111111109 // 30, 8) == "07081804"
    assert totp.code_at(RFC_SECRET, 2000000000 // 30, 8) == "69279037"


def test_totp_verify_window_and_replay():
    now = 1_800_000_000
    code = totp.code_at(RFC_SECRET, now // 30)
    step = totp.verify(RFC_SECRET, code, now=now)
    assert step == now // 30
    assert totp.verify(RFC_SECRET, code, now=now + 30) == step  # one step of clock drift is fine
    assert totp.verify(RFC_SECRET, code, now=now + 120) is None  # too old
    assert totp.verify(RFC_SECRET, code, now=now, last_counter=step) is None  # can't be reused
    assert totp.verify(RFC_SECRET, "12345", now=now) is None
    assert totp.verify(RFC_SECRET, "abcdef", now=now) is None
    assert totp.uri(RFC_SECRET).startswith("otpauth://totp/")


def test_login_requires_code_when_2fa_on(monkeypatch):
    monkeypatch.setattr(settings, "totp_secret", RFC_SECRET)
    monkeypatch.setattr(auth, "_last_totp_counter", -1)
    auth._fails.clear()
    good = totp.code_at(RFC_SECRET, int(__import__("time").time()) // 30)
    assert not auth.check_login("1.1.1.1", "test-pass", "")
    assert not auth.check_login("1.1.1.1", "test-pass", "000000" if good != "000000" else "111111")
    assert auth.check_login("1.1.1.1", "test-pass", good)
    assert not auth.check_login("1.1.1.1", "test-pass", good)  # replay refused
    auth._fails.clear()


def test_login_page_shows_code_field_only_with_2fa(monkeypatch):
    c = TestClient(app)
    assert 'data-2fa="0"' in c.get("/login").text
    monkeypatch.setattr(settings, "totp_secret", RFC_SECRET)
    assert 'data-2fa="1"' in c.get("/login").text


def test_global_throttle():
    auth._fails.clear()
    for i in range(auth.GLOBAL_MAX_FAILS):
        auth.check_login(f"10.0.0.{i}", "nope")
    assert auth.locked_out("10.9.9.9")  # a fresh address is still blocked
    auth._fails.clear()


def test_public_mode_refuses_weak_setup(monkeypatch):
    monkeypatch.setattr(settings, "public_url", "https://example.org")
    monkeypatch.setattr(settings, "totp_secret", "")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    problems = " ".join(auth.startup_problems())
    assert "at least 12" in problems and "SECRET_KEY" in problems and "TOTP_SECRET" in problems
    monkeypatch.setattr(auth, "_password", "a-long-enough-password")
    monkeypatch.setattr(auth, "_generated", False)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setattr(settings, "totp_secret", RFC_SECRET)
    assert auth.startup_problems() == []
    monkeypatch.setattr(settings, "public_url", "http://127.0.0.1:8000")
    monkeypatch.setattr(auth, "_password", "short")
    assert auth.startup_problems() == []  # your own machine: no extra requirements


def test_security_headers_and_health():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True  # reachable without logging in
    for h in ("Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy"):
        assert h in r.headers
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_cross_site_posts_blocked():
    c = TestClient(app)
    c.post("/login", data={"password": "test-pass"})
    r = c.post("/api/trading/kill", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    ok = c.post("/api/alerts/seen", headers={"Origin": "http://testserver"})
    assert ok.status_code == 200
    r = TestClient(app).post("/login", data={"password": "test-pass"}, headers={"Origin": "https://evil.example"},
                             follow_redirects=False)
    assert r.status_code == 403


def test_instance_lock_is_exclusive(tmp_path):
    a, b = InstanceLock(str(tmp_path)), InstanceLock(str(tmp_path))
    assert a.acquire()
    assert not b.acquire()  # a second copy can't trade
    a.release()
    assert b.acquire()
    b.release()
