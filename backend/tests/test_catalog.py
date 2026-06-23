"""Tests for catalog/deals repository methods."""

import tempfile

from backend.app.database import Database
from backend.app.domain import SearchResult
from backend.app.repository import Repository


def _deal(
    product_id: str,
    name: str,
    discount: int,
    current: int,
    original: int,
) -> SearchResult:
    return SearchResult(
        product_id=product_id,
        locale="en-us",
        name=name,
        store_url=f"https://store.playstation.com/en-us/product/{product_id}",
        image_url="https://example.test/img.png",
        platforms=["PS5"],
        currency="USD",
        current_price_cents=current,
        current_price_formatted=f"${current / 100:.2f}",
        original_price_cents=original,
        original_price_formatted=f"${original / 100:.2f}",
        discount_text=f"-{discount}%",
    )


def test_upsert_catalog_and_list_deals():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(f"{tmpdir}/test.sqlite3")
        db.migrate()
        repo = Repository(db)

        repo.upsert_catalog_entries([
            _deal("UP0001-PPSA00001_00-GAMEONE", "Game One", 50, 2999, 5999),
            _deal("UP0002-PPSA00002_00-GAMETWO", "Game Two", 0, 6999, 6999),
        ])

        sale_items, sale_total = repo.list_deals(min_discount=10, on_sale_only=True)
        assert sale_total == 1

        all_items, all_total = repo.list_deals(on_sale_only=False)
        assert all_total == 2

        full_price, full_total = repo.list_deals(min_discount=0, on_sale_only=False)
        assert full_total == 2

        suggestions = repo.suggest_names("Game", limit=5)
        assert len(suggestions) == 2

        tracked = repo.mark_tracked(sale_items[0]["id"])
        assert tracked is not None
        assert tracked["is_tracked"] is True
