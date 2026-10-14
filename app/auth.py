"""Single-user lock: a password, an optional authenticator code, a signed session cookie,
and login throttling.

Set APP_PASSWORD (and ideally SECRET_KEY) in your environment. If APP_PASSWORD is missing on
your own machine, a random one is printed at startup so the site is never open. On a public
https address, a strong password and 2-step login (TOTP_SECRET) are required: see startup_problems().
"""
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import totp
from app.config import is_public, settings

COOKIE = "sd_session"
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "14"))
MAX_FAILS, LOCKOUT_SECONDS = 5, 15 * 60
GLOBAL_MAX_FAILS = 20  # across all addresses: stops guessing spread over many IPs
MIN_PUBLIC_PASSWORD = 12
# The Robinhood OAuth callback must be reachable without our cookie (it's a cross-site redirect);
# it only completes a login you started, validated by the OAuth state parameter.
PUBLIC_PATHS = {"/login", "/healthz", "/static/login.html", "/static/login.js", "/static/styles.css",
                "/static/theme.js", "/broker/robinhood/callback"}

_password = os.getenv("APP_PASSWORD")
_generated = not _password
if _generated:
    _password = secrets.token_urlsafe(12)
    print(f"\n*** APP_PASSWORD not set. Temporary password for this run: {_password} ***\n", flush=True)
# Changing the password, SECRET_KEY or TOTP secret logs out every existing session.
_key = hashlib.sha256((os.getenv("SECRET_KEY", "") + "|" + _password + "|" + settings.totp_secret).encode()).digest()
_fails: dict[str, list[float]] = {}
_last_totp_counter = -1


def startup_problems() -> list[str]:
    """Settings that make it unsafe to run on the public internet."""
    if not is_public():
        return []
    problems = []
    if _generated or len(_password) < MIN_PUBLIC_PASSWORD:
        problems.append(f"APP_PASSWORD must be set and at least {MIN_PUBLIC_PASSWORD} characters on a public site")
    if not os.getenv("SECRET_KEY"):
        problems.append("SECRET_KEY must be set on a public site (any long random text)")
    if not settings.totp_secret and os.getenv("ALLOW_NO_2FA") != "1":
        problems.append("2-step login is required on a public site: run `python -m app.totp` and set TOTP_SECRET")
    return problems


def two_factor() -> bool:
    return bool(settings.totp_secret)


def _sign(payload: str) -> str:
    return hmac.new(_key, payload.encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    expires = str(int(time.time()) + SESSION_DAYS * 86400)
    return f"{expires}.{_sign(expires)}"


def valid_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expires, sig = token.split(".", 1)
    return hmac.compare_digest(sig, _sign(expires)) and expires.isdigit() and int(expires) > time.time()


def _recent(key: str) -> list[float]:
    recent = [t for t in _fails.get(key, []) if time.time() - t < LOCKOUT_SECONDS]
    _fails[key] = recent
    return recent


def locked_out(ip: str) -> bool:
    return len(_recent(ip)) >= MAX_FAILS or len(_recent("*")) >= GLOBAL_MAX_FAILS


def check_login(ip: str, password: str, code: str = "") -> bool:
    global _last_totp_counter
    ok = hmac.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(_password.encode()).digest())
    if ok and two_factor():
        counter = totp.verify(settings.totp_secret, code, last_counter=_last_totp_counter)
        ok = counter is not None
        if ok:
            _last_totp_counter = counter  # each code works once
    if ok:
        _fails.pop(ip, None)
    else:
        now = time.time()
        _fails.setdefault(ip, []).append(now)
        _fails.setdefault("*", []).append(now)
    return ok


def cookie_secure() -> bool:
    return settings.public_url.startswith("https://")


async def middleware(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS or valid_token(request.cookies.get(COOKIE)):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "not logged in"}, status_code=401)
    return RedirectResponse("/login", status_code=303)
