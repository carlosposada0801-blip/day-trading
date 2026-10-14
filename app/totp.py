"""Time-based one-time codes (RFC 6238), the 6-digit codes from Google Authenticator, Authy,
1Password, etc. Run `python -m app.totp` to create a secret and add it to your authenticator."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, counter: int, digits: int = 6) -> str:
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** digits).zfill(digits)


def verify(secret: str, code: str, now: float | None = None, window: int = 1, last_counter: int = -1) -> int | None:
    """The matching time step if `code` is valid (allowing +/- window steps of clock drift) and
    newer than last_counter (so a code can't be replayed), else None."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return None
    t = int((now if now is not None else time.time()) // 30)
    for c in range(t - window, t + window + 1):
        if c > last_counter and hmac.compare_digest(code_at(secret, c), code):
            return c
    return None


def uri(secret: str, account: str = "you", issuer: str = "Signal Desk") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}"


if __name__ == "__main__":
    s = new_secret()
    print("Add this to your authenticator app (choose 'enter a setup key'):\n")
    print(f"  Key:  {' '.join(s[i:i + 4] for i in range(0, len(s), 4))}")
    print("  Type: time-based, 6 digits\n")
    print(f"Or open this link on your phone: {uri(s)}\n")
    print(f"Then put this line in your .env and restart:\n\n  TOTP_SECRET={s}\n")
