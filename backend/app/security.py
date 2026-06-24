"""Shared security helpers.

Small pure functions used by auth routes and the API to avoid common web
security mistakes. No database or HTTP code here — easy to unit test.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Default dev-only proxy key — must never be used when PS_PRICE_PRODUCTION_MODE=true.
DEV_INTERNAL_API_KEY = "ps-price-local-proxy-key"

# Set by the Next.js proxy on upstream requests; blocks direct backend access with only the internal key.
API_CLIENT_HEADER = "x-ps-price-client"
API_CLIENT_VALUE = "1"

# Headers the Next.js proxy may forward to the backend.
PROXY_ALLOWED_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "accept-language",
        "content-type",
        "cookie",
        "authorization",
    }
)

# Maximum JSON body size accepted by the API (1 MiB).
MAX_REQUEST_BODY_BYTES = 1_048_576


def safe_redirect_path(value: str | None, *, default: str = "/") -> str:
    """Return a safe same-site redirect path, or ``default`` if input is suspicious."""
    if not value:
        return default
    path = value.strip()
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return default
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        return default
    return path


def user_is_admin(user: dict, settings) -> bool:
    """Return True if the user's email is listed in ``PS_PRICE_ADMIN_EMAILS``."""
    email = user.get("email", "").lower()
    return bool(email and email in settings.admin_email_list)


def internal_key_valid(settings, provided: str | None) -> bool:
    """Return True when the caller presented the configured internal API key."""
    if not settings.internal_api_key:
        return False
    return bool(provided and provided == settings.internal_api_key)


def proxy_client_valid(provided: str | None) -> bool:
    """Return True when the request was forwarded by the Next.js API proxy."""
    return provided == API_CLIENT_VALUE


def api_security_headers(*, production_mode: bool) -> dict[str, str]:
    """Standard security headers for JSON API responses."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Resource-Policy": "same-site",
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    }
    if production_mode:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers
