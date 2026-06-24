"""Integration test for 007 search editions via live store merge."""

from backend.app.domain import SearchResult


def test_search_007_includes_first_light_editions(client, monkeypatch):
    store_rows = [
        SearchResult(
            product_id="EP3969-PPSA11386_00-007FIRSTLIGHT000",
            locale="en-us",
            name="007 First Light",
            store_url="https://store.playstation.com/en-us/product/EP3969-PPSA11386_00-007FIRSTLIGHT000",
            image_url="https://image.api.playstation.com/example.png",
            platforms=["PS5"],
            currency="USD",
            current_price_cents=6999,
            current_price_formatted="$69.99",
            original_price_cents=6999,
            original_price_formatted="$69.99",
        ),
        SearchResult(
            product_id="EP3969-PPSA11386_00-007FLDELUXE00000",
            locale="en-us",
            name="007 First Light - Deluxe Edition",
            store_url="https://store.playstation.com/en-us/product/EP3969-PPSA11386_00-007FLDELUXE00000",
            image_url="https://image.api.playstation.com/example-deluxe.png",
            platforms=["PS5"],
            currency="USD",
            current_price_cents=7999,
            current_price_formatted="$79.99",
            original_price_cents=7999,
            original_price_formatted="$79.99",
        ),
        SearchResult(
            product_id="EP3969-PPSA11386_00-007FLDELUXEUPG00",
            locale="en-us",
            name="007 First Light - Deluxe Edition Upgrade",
            store_url="https://store.playstation.com/en-us/product/EP3969-PPSA11386_00-007FLDELUXEUPG00",
            image_url="https://image.api.playstation.com/example-upgrade.png",
            platforms=["PS5"],
            currency="USD",
            current_price_cents=1999,
            current_price_formatted="$19.99",
            original_price_cents=1999,
            original_price_formatted="$19.99",
        ),
    ]

    async def fake_store_search(query, locale=None, limit=10, force=False):
        assert query == "007"
        return store_rows

    monkeypatch.setattr(client.app.state.store_client, "search", fake_store_search)

    response = client.get("/api/search?q=007&limit=12")
    assert response.status_code == 200
    data = response.json()
    names = [row["name"] for row in data]
    assert "007 First Light" in names
    assert "007 First Light - Deluxe Edition" in names
    assert "007 First Light - Deluxe Edition Upgrade" in names
    assert names.index("007 First Light") < names.index("007 First Light - Deluxe Edition")
