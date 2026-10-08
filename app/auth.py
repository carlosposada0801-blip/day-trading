"""Single-user lock: one password, a signed session cookie, and login throttling.

Set APP_PASSWORD (and ideally SECRET_KEY) in your environment. If APP_PASSWORD is
missing a random one is generated and printed at startup, so the app is never open.
"""
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse


COOKIE = "sd_session"
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "14"))
MAX_FAILS, LOCKOUT_SECONDS = 5, 15 * 60
# The Robinhood OAuth callback must be reachable without our cookie (it's a cross-site redirect);
# it only completes a login you started, validated by the OAuth state parameter.
PUBLIC_PATHS = {"/login", "/static/login.html", "/static/styles.css", "/broker/robinhood/callback"}

_password = os.getenv("APP_PASSWORD")
if not _password:
    _password = secrets.token_urlsafe(12)
    print(f"\n*** APP_PASSWORD not set. Temporary password for this run: {_password} ***\n", flush=True)
# Changing the password (or SECRET_KEY) invalidates every existing session.
_key = hashlib.sha256((os.getenv("SECRET_KEY", "") + "|" + _password).encode()).digest()
_fails: dict[str, list[float]] = {}


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


def locked_out(ip: str) -> bool:
    recent = [t for t in _fails.get(ip, []) if time.time() - t < LOCKOUT_SECONDS]
    _fails[ip] = recent
    return len(recent) >= MAX_FAILS


def check_password(ip: str, attempt: str) -> bool:
    ok = hmac.compare_digest(hashlib.sha256(attempt.encode()).digest(),
                             hashlib.sha256(_password.encode()).digest())
    if ok:
        _fails.pop(ip, None)
    else:
        _fails.setdefault(ip, []).append(time.time())
    return ok


async def middleware(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS or valid_token(request.cookies.get(COOKIE)):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "not logged in"}, status_code=401)
    return RedirectResponse("/login", status_code=303)
