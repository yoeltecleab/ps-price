"""Resolve WebAuthn RP ID and allowed origins for the current deployment."""

from __future__ import annotations

from urllib.parse import urlparse

from backend.app.config import Settings


def effective_rp_id(settings: Settings) -> str:
    """RP ID must be a registrable domain suffix of the page origin."""
    if settings.webauthn_rp_id and settings.webauthn_rp_id not in {"localhost", "127.0.0.1"}:
        return settings.webauthn_rp_id
    host = urlparse(settings.frontend_url).hostname
    return host or settings.webauthn_rp_id or "localhost"


def effective_origins(settings: Settings, request_origin: str | None = None) -> list[str]:
    """Allowed origins for WebAuthn verification (includes request Origin when safe)."""
    origins = list(settings.webauthn_origin_list or [settings.webauthn_origin])
    if request_origin and request_origin not in origins:
        req_host = urlparse(request_origin).hostname
        fe_host = urlparse(settings.frontend_url).hostname
        if req_host and fe_host and req_host == fe_host:
            origins.append(request_origin.rstrip("/"))
    return origins
