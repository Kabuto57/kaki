"""Password hashing and token handling.

Hashing uses `bcrypt` directly rather than `passlib`. Passlib has not had a
release since 2020 and breaks against bcrypt 4.x when it tries to read the
version, which surfaces as a spurious "password cannot be longer than 72 bytes"
on perfectly ordinary passwords. Calling bcrypt directly is both simpler and
less to go wrong.

Bcrypt genuinely does ignore everything past 72 bytes, which would silently make
a long passphrase weaker than it looks. Pre-hashing with SHA-256 gives every
password a fixed 44-byte representation, so the whole thing is always used.

Two token types, deliberately:

* Access tokens are short-lived and sent on every request, so a leak has a small
  window.
* Refresh tokens are long-lived and only accepted at /auth/refresh. They carry a
  `typ` claim so a refresh token cannot be replayed as an access token — the
  classic mistake when both are signed with the same key.
"""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings
from app.core.errors import AuthError

settings = get_settings()

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


def _prepare(password: str) -> bytes:
    """SHA-256 then base64, so bcrypt sees a fixed-length input well under 72
    bytes and no part of a long passphrase is silently discarded."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed stored hash must fail closed, not raise into a 500.
        return False


def _create_token(subject: int, token_type: TokenType, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id, "access", timedelta(minutes=settings.access_token_ttl_minutes)
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.refresh_token_ttl_days)
    )


def decode_token(token: str, expect: TokenType) -> int:
    """Return the user id, or raise AuthError. Never returns None on failure —
    callers should not have to remember to check."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise AuthError("That session is not valid. Sign in again.")

    if payload.get("typ") != expect:
        raise AuthError("Wrong kind of token for this endpoint.")

    subject = payload.get("sub")
    if subject is None:
        raise AuthError("That session is not valid. Sign in again.")

    try:
        return int(subject)
    except (TypeError, ValueError):
        raise AuthError("That session is not valid. Sign in again.")
