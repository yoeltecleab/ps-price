from datetime import UTC, datetime

from backend.app.database import Database
from backend.app.domain import ProductSnapshot
from backend.app.repository import Repository


def test_repository_upserts_games_and_records_history(tmp_path):
    db = Database(str(tmp_path / "test.sqlite3"))
    db.migrate()
    repo = Repository(db)
    snapshot = ProductSnapshot(
        product_id="UP0000-PPSA00000_00-EXAMPLEGAME0000",
        locale="en-us",
        name="Example Game",
        category="Game",
        image_url=None,
        store_url="https://store.playstation.com/en-us/product/UP0000-PPSA00000_00-EXAMPLEGAME0000",
        currency="USD",
        current_price_cents=2999,
        current_price_formatted="$29.99",
        original_price_cents=5999,
        original_price_formatted="$59.99",
        discount_text="Save 50%",
        availability="available",
        fetched_at=datetime.now(UTC),
        raw_source_hash="abc",
        price_source="test",
    )

    game, previous_price = repo.upsert_game_snapshot(snapshot)

    assert previous_price is None
    assert game["current_price_cents"] == 2999
    assert len(repo.get_history(game["id"])) == 1
