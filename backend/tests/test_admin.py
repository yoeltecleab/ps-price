"""Admin API endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.auth_repository import AuthRepository
from backend.app.auth_service import AuthService
from backend.app.config import Settings
from backend.app.main import app
from backend.app.notifier import EmailNotifier
from backend.app.ps_store import PlayStationStoreClient
from backend.app.repository import Repository
from backend.app.rate_limit import rate_limiter
from backend.app.scheduler import PriceScheduler
from backend.app.service import PriceService


def _wire_app(temp_db, settings):
    repo = Repository(temp_db)
    auth_repo = AuthRepository(temp_db)
    store_client = PlayStationStoreClient(settings)
    notifier = EmailNotifier(settings, repo)
    auth_service = AuthService(settings, auth_repo, repo, notifier)
    service = PriceService(settings, repo, store_client, notifier, auth_service)
    scheduler = PriceScheduler(settings, service)

    app.state.settings = settings
    app.state.db = temp_db
    app.state.repo = repo
    app.state.auth_repo = auth_repo
    app.state.auth_service = auth_service
    app.state.store_client = store_client
    app.state.notifier = notifier
    app.state.service = service
    app.state.scheduler = scheduler
    rate_limiter.reset()
    return auth_repo


@pytest.fixture
def admin_client(temp_db, settings):
    settings = Settings(
        **{
            **settings.model_dump(),
            "admin_emails": "admin@example.com",
        }
    )
    auth_repo = _wire_app(temp_db, settings)
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={
            "email": "admin@example.com",
            "password": "passwordpassword",
            "display_name": "Admin",
        },
    )
    assert response.status_code == 201
    auth_repo.mark_email_verified(response.json()["user"]["id"])
    yield client


def test_admin_overview_requires_admin(admin_client):
    response = admin_client.get("/api/admin/overview")
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert "catalog" in data
    assert "insights" in data
    assert "system" in data
    assert data["users"]["total"] >= 1


def test_admin_overview_forbidden_for_non_admin(temp_db, settings):
    settings = Settings(
        **{
            **settings.model_dump(),
            "admin_emails": "admin@example.com",
        }
    )
    _wire_app(temp_db, settings)
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "passwordpassword",
            "display_name": "User",
        },
    )
    assert response.status_code == 201
    assert client.get("/api/admin/overview").status_code == 403


def test_admin_list_users(admin_client):
    response = admin_client.get("/api/admin/users")
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_admin_insights(admin_client):
    response = admin_client.get("/api/admin/insights")
    assert response.status_code == 200
    assert "recent_users" in response.json()
