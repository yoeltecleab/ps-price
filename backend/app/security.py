"""Shared security helpers.

Small pure functions used by auth routes and the API to avoid common web
security mistakes. No database or HTTP code here — easy to unit test.
"""

from __future__ import annotations

from urllib.parse import urlparse


def safe_redirect_path(value: str | None, *, default: str = "/") -> str:
    """Return a safe same-site redirect path, or ``default`` if input is suspicious.

    **Open redirect** attacks trick users into logging in, then send them to a
    fake site. We only allow paths that start with a single ``/`` on our own site.

    Rejected examples:
      - ``https://evil.com``  (absolute URL)
      - ``//evil.com``        (protocol-relative URL)
      - ``/\\evil.com``       (backslash tricks)

    Args:
        value: The ``?next=`` query parameter from the frontend.
        default: Where to send the user if ``value`` is missing or unsafe.

    Returns:
        A relative path like ``/library`` or ``default``.
    """
    if not value:
        return default
    path = value.strip()
    # Must be a relative path on our site, not "//other-host".
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return default
    parsed = urlparse(path)
    # urlparse catches sneaky "http:..." style paths.
    if parsed.scheme or parsed.netloc:
        return default
    return path


def user_is_admin(user: dict, settings) -> bool:
    """Return True if the user's email is listed in ``PS_PRICE_ADMIN_EMAILS``.

    Admins can trigger manual catalog sync and other privileged operations.
    The email list is configured in ``config.Settings.admin_emails``.

    Args:
        user: Dict with at least an ``email`` key (from session).
        settings: App settings object with ``admin_email_list`` property.
    """
    email = user.get("email", "").lower()
    return bool(email and email in settings.admin_email_list)
