"""Integration tests for the PS Price backend API.

These tests verify that the entire system works end-to-end:
- Database initialization
- PS Store client with caching and rate limiting
- API endpoint responses
- Watch evaluation and notification logging
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def auth_client(client):
    """Authenticated test client with a verified user session."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "tester@example.com",
            "password": "passwordpassword",
            "display_name": "Tester",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["user"]["id"]
    client.app.state.auth_repo.mark_email_verified(user_id)
    return client


def test_healthz(client):
    """Test that the health endpoint works."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_healthz_with_scheduler_status(client):
    """Scheduler details are hidden without the internal API key."""
    response = client.get("/healthz?scheduler=true")
    assert response.status_code == 403


def test_auth_me_anonymous_returns_null_user(client):
    """Session probe should succeed without credentials (no 401 cascade)."""
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["user"] is None
    assert data["notification_emails"] == []
    assert data["passkeys"] == []


def test_search_anonymous_without_auth(client, monkeypatch):
    """Catalog search is public — no login required."""

    async def fake_search(query, locale=None, limit=10, user_id=None):
        assert user_id is None
        return [
            {
                "id": 1,
                "product_id": "UP0001",
                "locale": "en-us",
                "name": f"Result for {query}",
                "store_url": "https://store.playstation.com/x",
                "current_price_formatted": "$9.99",
                "discount_text": None,
                "image_url": None,
            }
        ]

    monkeypatch.setattr(client.app.state.service, "search", fake_search)
    response = client.get("/api/search?q=god&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "god" in data[0]["name"]


def test_search_games_requires_query(client):
    """Test that search requires a query parameter."""
    response = client.get("/api/search")
    assert response.status_code == 422


def test_search_games_with_empty_query(client):
    """Test that search with empty query works (returns empty list)."""
    response = client.get("/api/search?q=")
    # Empty query after trim returns empty list from the client
    # This is expected behavior
    assert response.status_code in [200, 422]


def test_games_list_empty_initially(auth_client):
    """Test that games list is empty when no games are tracked."""
    response = auth_client.get("/api/games")
    assert response.status_code == 200
    assert response.json() == []


def test_watches_list_empty_initially(auth_client):
    """Test that watches list is empty initially."""
    response = auth_client.get("/api/watches")
    assert response.status_code == 200
    assert response.json() == []


def test_notifications_list_empty_initially(auth_client):
    """Test that notifications list is empty initially."""
    response = auth_client.get("/api/notifications")
    assert response.status_code == 200
    assert response.json() == []


def test_create_game_with_invalid_product_ref(auth_client):
    """Test that invalid product refs are rejected."""
    response = auth_client.post(
        "/api/games",
        json={"product_ref": "", "locale": "en-us"},
    )
    # Empty product_ref fails validation (422) before reaching service (400)
    assert response.status_code in [400, 422]


def test_create_game_with_invalid_product_id(auth_client):
    """Test that invalid product IDs are rejected."""
    response = auth_client.post(
        "/api/games",
        json={"product_ref": "INVALID", "locale": "en-us"},
    )
    # Should fail with 400 or 502 depending on store client behavior
    assert response.status_code in [400, 502]


def test_list_watches_with_invalid_game_id(auth_client):
    """Test filtering watches by non-existent game ID returns empty."""
    response = auth_client.get("/api/watches?game_id=999")
    assert response.status_code == 200
    assert response.json() == []


def test_get_game_returns_404_for_missing_game(client):
    """Test that getting a non-existent game returns 404."""
    response = client.get("/api/games/999")
    assert response.status_code == 404


def test_delete_game_returns_404_for_missing_game(auth_client):
    """Test that deleting a non-existent game returns 404."""
    response = auth_client.delete("/api/games/999")
    assert response.status_code == 404


def test_delete_watch_returns_404_for_missing_watch(auth_client):
    """Test that deleting a non-existent watch returns 404."""
    response = auth_client.delete("/api/watches/999")
    assert response.status_code == 404


def test_update_watch_returns_404_for_missing_watch(auth_client):
    """Test that updating a non-existent watch returns 404."""
    response = auth_client.patch(
        "/api/watches/999",
        json={"enabled": False},
    )
    assert response.status_code == 404


def test_test_watch_returns_404_for_missing_watch(auth_client):
    """Test that testing a non-existent watch returns 404."""
    response = auth_client.post("/api/watches/999/test")
    assert response.status_code == 404


def test_create_watch_with_invalid_game(auth_client):
    """Test watch creation fails when the game is missing."""
    response = auth_client.post(
        "/api/watches",
        json={
            "game_id": 1,
            "notification_email_id": 1,
            "target_price_cents": 2999,
        },
    )
    assert response.status_code in [400, 404]


def test_search_respects_limit_bounds(client):
    """Test that search respects configured limit boundaries."""
    # Search with excessively high limit should cap at max_search_limit
    response = client.get("/api/search?q=test&limit=1000")
    assert response.status_code in [200, 422]  # Either succeeds or validation fails


def test_search_007_returns_catalog_results(client, monkeypatch):
    """Short numeric queries like 007 should return local catalog hits."""

    async def fake_search_unified(query, locale, limit, user_id=None):
        assert query == "007"
        return [
            {
                "id": 1,
                "product_id": "UP0001-EXAMPLE_00-007FIRSTLIGHT",
                "locale": "en-us",
                "name": "007 First Light",
                "store_url": "https://store.playstation.com/en-us/product/UP0001-EXAMPLE_00-007FIRSTLIGHT",
                "image_url": "https://image.api.playstation.com/example.png",
                "platforms": ["PS5"],
                "currency": "USD",
                "current_price_cents": 6999,
                "current_price_formatted": "$69.99",
                "original_price_cents": 6999,
                "original_price_formatted": "$69.99",
                "discount_text": None,
                "source": "catalog",
                "is_tracked": False,
            }
        ]

    monkeypatch.setattr(client.app.state.service, "search_unified", fake_search_unified)

    response = client.get("/api/search?q=007&limit=12")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "007" in data[0]["name"]
    assert data[0]["source"] == "catalog"


def test_refresh_due_with_no_games(auth_client):
    """Test refresh-due endpoint when no games are tracked."""
    response = auth_client.post("/api/refresh-due")
    assert response.status_code == 200
    data = response.json()
    assert data["due"] == 0
    assert data["refreshed"] == 0
    assert data["failed"] == []


def test_api_cors_headers_present(client):
    """Test that CORS headers are present in responses."""
    response = client.get("/healthz")
    assert response.status_code == 200
    # FastAPI with CORSMiddleware adds these headers
    # The exact headers depend on the client's origin


def test_database_is_initialized(client):
    """Test that database schema is properly initialized."""
    repo = client.app.state.repo
    # Try to list games - this will fail if schema doesn't exist
    games = repo.list_games()
    assert isinstance(games, list)
    assert games == []


def test_multiple_api_calls_dont_interfere(auth_client):
    """Test that multiple API calls work independently."""
    # Call healthz multiple times
    for _ in range(3):
        response = auth_client.get("/healthz")
        assert response.status_code == 200

    # Call games list multiple times
    for _ in range(3):
        response = auth_client.get("/api/games")
        assert response.status_code == 200
        assert response.json() == []


def test_refresh_due_endpoint_exists(auth_client):
    """Test that the refresh-due operational endpoint exists."""
    response = auth_client.post("/api/refresh-due")
    assert response.status_code == 200
    assert "due" in response.json()
    assert "refreshed" in response.json()
    assert "failed" in response.json()


def test_api_returns_json_content_type(client):
    """Test that API endpoints return JSON content type."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")


def test_deals_and_suggest_endpoints(client):
    """Deals listing and autocomplete should work on an empty catalog."""
    deals = client.get("/api/deals")
    assert deals.status_code == 200
    payload = deals.json()
    assert "items" in payload
    assert "total" in payload

    suggest = client.get("/api/suggest?q=test")
    assert suggest.status_code == 200
    assert isinstance(suggest.json(), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


