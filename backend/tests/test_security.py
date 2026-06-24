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
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings(
            production_mode=True,
            database_url="",
            admin_emails="admin@example.com",
            cookie_secure=True,
            frontend_url="https://psprice.example.com",
            webauthn_rp_id="psprice.example.com",
            webauthn_origin="https://psprice.example.com",
            jwt_secret="production-secret-at-least-32-characters-long",
            internal_api_key="production-internal-api-key-at-least-32-chars",
            cors_origins="https://psprice.example.com",
        ).validate_production_settings()

    with pytest.raises(RuntimeError, match="ADMIN_EMAILS"):
        Settings(
            production_mode=True,
            database_url="postgresql://user:pass@localhost:5432/psprice",
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
            database_url="postgresql://user:pass@localhost:5432/psprice",
            admin_emails="admin@example.com",
            cookie_secure=True,
            frontend_url="https://psprice.example.com",
            webauthn_rp_id="psprice.example.com",
            webauthn_origin="https://psprice.example.com",
        ).validate_production_settings()

    Settings(
        production_mode=True,
        database_url="postgresql://user:pass@localhost:5432/psprice",
        admin_emails="admin@example.com",
        cookie_secure=True,
        frontend_url="https://psprice.example.com",
        webauthn_rp_id="psprice.example.com",
        webauthn_origin="https://psprice.example.com",
        jwt_secret="production-secret-at-least-32-characters-long",
        internal_api_key="production-internal-api-key-at-least-32-chars",
        cors_origins="https://psprice.example.com",
    ).validate_production_settings()


def test_internal_key_valid() -> None:
    from backend.app.security import internal_key_valid

    settings = Settings(internal_api_key="super-secret-internal-key-32chars-min")
    assert internal_key_valid(settings, "super-secret-internal-key-32chars-min")
    assert not internal_key_valid(settings, "wrong")
    assert not internal_key_valid(Settings(internal_api_key=""), "anything")


def test_healthz_scheduler_requires_internal_key() -> None:
    from fastapi.testclient import TestClient

    from backend.app.main import app

    app.state.settings = Settings(
        internal_api_key="test-internal-api-key-at-least-32-characters",
        production_mode=False,
    )

    class _Scheduler:
        running = False

    app.state.scheduler = _Scheduler()
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz?scheduler=true").status_code == 403
    ok = client.get(
        "/healthz?scheduler=true",
        headers={"X-PS-Price-Internal": "test-internal-api-key-at-least-32-characters"},
    )
    assert ok.status_code == 200
    assert "scheduler_running" in ok.json()


def test_production_rejects_weak_internal_api_key() -> None:
    base = dict(
        production_mode=True,
        database_url="postgresql://user:pass@localhost:5432/psprice",
        admin_emails="admin@example.com",
        cookie_secure=True,
        frontend_url="https://psprice.example.com",
        webauthn_rp_id="psprice.example.com",
        webauthn_origin="https://psprice.example.com",
        jwt_secret="production-secret-at-least-32-characters-long",
        cors_origins="https://psprice.example.com",
    )
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        Settings(**base, internal_api_key="").validate_production_settings()
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        Settings(**base, internal_api_key="ps-price-local-proxy-key").validate_production_settings()


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
