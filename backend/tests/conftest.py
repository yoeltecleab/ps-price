"""Shared pytest fixtures for database-backed tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.app.auth_repository import AuthRepository
from backend.app.auth_service import AuthService
from backend.app.config import Settings
from backend.app.database import Database, create_database
from backend.app.main import app
from backend.app.notifier import EmailNotifier
from backend.app.ps_store import PlayStationStoreClient
from backend.app.repository import Repository
from backend.app.rate_limit import rate_limiter
from backend.app.scheduler import PriceScheduler
from backend.app.service import PriceService


@pytest.fixture
def temp_db():
    """Fresh PostgreSQL schema for each test."""
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://psprice:psprice@localhost:5432/psprice_test",
    )
    db = Database(url)
    db.drop_all()
    db.create_all()
    yield db
    db.drop_all()


@pytest.fixture
def settings(temp_db):
    return Settings(
        database_url=temp_db.url,
        scheduler_enabled=False,
        cors_origins="*",
        require_email_verification=False,
        admin_emails="tester@example.com",
        jwt_secret="test-jwt-secret-must-be-at-least-32-chars",
        internal_api_key="",
    )


@pytest.fixture
def client(temp_db, settings):
    """FastAPI test client wired to an isolated Postgres database."""
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
    return TestClient(app)


@pytest.fixture
def db_factory(temp_db):
    return create_database
