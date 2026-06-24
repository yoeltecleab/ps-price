"""Create and verify JSON Web Tokens (JWT) for API authentication.

JWTs are signed strings the server can verify without a database lookup on every
request (for access tokens). We use **two** token types:

- **Access token** — short-lived; sent on each API call (cookie or Bearer header).
  Contains user id, email-verified flag, and a ``ver`` (token version) claim.
- **Refresh token** — long-lived; used only to obtain a new access token.
  Its ``jti`` (unique id) is stored in SQLite so logout/password change can revoke it.

Both are signed with ``PS_PRICE_JWT_SECRET`` using HS256.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

ACCESS_TYPE = "access"
REFRESH_TYPE = "refresh"


class JwtError(ValueError):
    """Raised when a JWT is missing, expired, or has the wrong type."""


def create_access_token(settings, user: dict) -> str:
    """Build a signed access JWT for ``user`` (database row dict)."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "ev": bool(user.get("email_verified_at")),
        "hp": bool(user.get("password_hash")),
        "ver": int(user.get("token_version") or 0),
        "type": ACCESS_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(settings, user_id: int, jti: str) -> str:
    """Build a signed refresh JWT; ``jti`` is stored hashed in the sessions table."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": REFRESH_TYPE,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_ttl_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(settings, token: str, *, expected_type: str) -> dict[str, Any]:
    """Verify signature and expiry; ensure ``type`` claim matches."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise JwtError("invalid token") from exc
    if payload.get("type") != expected_type:
        raise JwtError("invalid token")
    return payload
