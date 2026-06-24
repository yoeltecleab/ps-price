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


def test_admin_list_watches_returns_flat_rows(admin_client, temp_db):
    from backend.app.db.util import utc_now_iso
    from backend.app.db.models import Game, Watch

    repo = admin_client.app.state.repo
    now = utc_now_iso()
    with temp_db.session() as session:
        game = Game(
            product_id="admin-watch-test",
            locale="en-us",
            name="Watch Me",
            store_url="https://example.com",
            created_at=now,
            updated_at=now,
        )
        session.add(game)
        session.flush()
        session.add(
            Watch(
                game_id=game.id,
                email="watch@test.com",
                enabled=1,
                notify_on_any_drop=0,
                created_at=now,
                updated_at=now,
            )
        )

    response = admin_client.get("/api/admin/watches")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    row = payload["items"][0]
    assert "id" in row
    assert row["game_name"] == "Watch Me"
    assert row["email"] == "watch@test.com"


def test_admin_list_notifications_returns_flat_rows(admin_client, temp_db):
    from backend.app.db.util import utc_now_iso
    from backend.app.db.models import Game, Notification

    now = utc_now_iso()
    with temp_db.session() as session:
        game = Game(
            product_id="admin-notif-test",
            locale="en-us",
            name="Notify Me",
            store_url="https://example.com",
            created_at=now,
            updated_at=now,
        )
        session.add(game)
        session.flush()
        session.add(
            Notification(
                game_id=game.id,
                email="notify@test.com",
                subject="Price drop",
                body="body",
                status="sent",
                created_at=now,
            )
        )

    response = admin_client.get("/api/admin/notifications")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    row = payload["items"][0]
    assert row["id"] is not None
    assert row["subject"] == "Price drop"
    assert row["body"] == "body"
    assert row["game_name"] == "Notify Me"


def test_admin_list_library(admin_client, temp_db):
    from sqlalchemy import select

    from backend.app.db.util import utc_now_iso
    from backend.app.db.models import Game, User, UserLibrary

    now = utc_now_iso()
    with temp_db.session() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        game = Game(
            product_id="admin-lib-test",
            locale="en-us",
            name="Library Game",
            store_url="https://example.com",
            created_at=now,
            updated_at=now,
        )
        session.add(game)
        session.flush()
        session.add(UserLibrary(user_id=user.id, game_id=game.id, created_at=now))

    response = admin_client.get("/api/admin/library")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["game_name"] == "Library Game"


def test_admin_unverified_user_forbidden(temp_db, settings):
    settings = Settings(
        **{
            **settings.model_dump(),
            "admin_emails": "admin@example.com",
            "require_email_verification": True,
        }
    )
    _wire_app(temp_db, settings)
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
    assert client.get("/api/admin/overview").status_code == 403


def test_admin_list_sessions(admin_client, temp_db):
    from sqlalchemy import select

    from backend.app.db.util import utc_now_iso
    from backend.app.db.models import RefreshSession, User

    now = utc_now_iso()
    with temp_db.session() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        session.add(
            RefreshSession(
                user_id=user.id,
                token_hash="hash",
                expires_at=now,
                created_at=now,
                user_agent="TestAgent",
                ip_address="127.0.0.1",
            )
        )

    response = admin_client.get("/api/admin/sessions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["user_email"] == "admin@example.com"
