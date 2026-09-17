"""Shared-credential auth for the dashboard HTTP surface.

Session cookie = `<expiry_ts>.<hex HMAC-SHA256(secret, expiry_ts)>` with the
secret derived from DASHBOARD_PASSWORD (changing the password invalidates all
sessions). No server-side session store: the signature and expiry carry all
state.
"""

import hashlib
import hmac
import time

COOKIE_NAME = "dashboard_session"
SESSION_MAX_AGE_S = 12 * 3600


def _secret(password: str) -> bytes:
    return hashlib.sha256(password.encode()).digest()


def _signature(secret: bytes, expiry_text: str) -> str:
    return hmac.new(secret, expiry_text.encode(), hashlib.sha256).hexdigest()


def sign_session(password: str, now: float | None = None) -> str:
    expiry = int((now if now is not None else time.time()) + SESSION_MAX_AGE_S)
    expiry_text = str(expiry)
    return f"{expiry_text}.{_signature(_secret(password), expiry_text)}"


def verify_session(cookie: str, password: str, now: float | None = None) -> bool:
    try:
        expiry_text, _, signature = cookie.partition(".")
        int(expiry_text)
    except ValueError:
        return False
    if not hmac.compare_digest(signature, _signature(_secret(password), expiry_text)):
        return False
    return (now if now is not None else time.time()) < int(expiry_text)


def password_matches(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())
