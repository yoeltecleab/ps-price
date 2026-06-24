"""Security helper tests."""

from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.security import safe_redirect_path, user_is_admin


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "/"),
        ("", "/"),
        ("/library", "/library"),
        ("/auth/login?next=%2F", "/auth/login?next=%2F"),
        ("//evil.com", "/"),
        ("https://evil.com", "/"),
        ("/\\evil", "/"),
        ("\\evil", "/"),
    ],
)
def test_safe_redirect_path(value: str | None, expected: str) -> None:
    assert safe_redirect_path(value) == expected


def test_user_is_admin() -> None:
    settings = Settings(admin_emails="admin@example.com,ops@example.com")
    assert user_is_admin({"email": "admin@example.com"}, settings)
    assert user_is_admin({"email": "OPS@example.com"}, settings)
    assert not user_is_admin({"email": "user@example.com"}, settings)


def test_production_settings_validation() -> None:
    with pytest.raises(RuntimeError, match="ADMIN_EMAILS"):
        Settings(
            production_mode=True,
            admin_emails="",
            cookie_secure=True,
            frontend_url="https://psprice.example.com",
            webauthn_rp_id="psprice.example.com",
            webauthn_origin="https://psprice.example.com",
            jwt_secret="x" * 32,
        ).validate_production_settings()

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings(
            production_mode=True,
            admin_emails="admin@example.com",
            cookie_secure=True,
            frontend_url="https://psprice.example.com",
            webauthn_rp_id="psprice.example.com",
            webauthn_origin="https://psprice.example.com",
        ).validate_production_settings()

    Settings(
        production_mode=True,
        admin_emails="admin@example.com",
        cookie_secure=True,
        frontend_url="https://psprice.example.com",
        webauthn_rp_id="psprice.example.com",
        webauthn_origin="https://psprice.example.com",
        jwt_secret="production-secret-at-least-32-characters-long",
    ).validate_production_settings()


def test_jwt_access_and_refresh_roundtrip() -> None:
    from backend.app.jwt_tokens import REFRESH_TYPE, create_access_token, create_refresh_token, decode_token

    settings = Settings(jwt_secret="test-jwt-secret-must-be-at-least-32-chars")
    user = {
        "id": 1,
        "email": "user@example.com",
        "email_verified_at": "2026-01-01T00:00:00+00:00",
        "password_hash": "hash",
        "token_version": 2,
    }
    access = create_access_token(settings, user)
    payload = decode_token(settings, access, expected_type="access")
    assert payload["sub"] == "1"
    assert payload["ver"] == 2

    refresh = create_refresh_token(settings, 1, "jti-abc")
    refresh_payload = decode_token(settings, refresh, expected_type=REFRESH_TYPE)
    assert refresh_payload["jti"] == "jti-abc"
