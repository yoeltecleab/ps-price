"""Tests for database row serialization helpers."""

from __future__ import annotations

from sqlalchemy import select

from backend.app.database import Database
from backend.app.db.models import Game, Notification, Watch
from backend.app.db.util import as_dict, utc_now_iso
from backend.app.repository import Repository


def test_as_dict_flattens_row_mapping_with_orm_entity(temp_db):
    now = utc_now_iso()
    with temp_db.session() as session:
        game = Game(
            product_id="util-test",
            locale="en-us",
            name="Flatten Me",
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

    repo = Repository(temp_db)
    items, _ = repo.list_watches_admin()
    row = items[0]
    assert "Watch" not in row
    assert row["id"] is not None
    assert row["email"] == "watch@test.com"
    assert row["game_name"] == "Flatten Me"


def test_as_dict_flattens_notification_join_rows(temp_db):
    now = utc_now_iso()
    with temp_db.session() as session:
        game = Game(
            product_id="notif-util",
            locale="en-us",
            name="Notify Game",
            store_url="https://example.com",
            created_at=now,
            updated_at=now,
        )
        session.add(game)
        session.flush()
        session.add(
            Notification(
                game_id=game.id,
                email="user@test.com",
                subject="Hello",
                body="Email body",
                status="sent",
                created_at=now,
            )
        )

    repo = Repository(temp_db)
    items, _ = repo.list_notifications_admin()
    row = items[0]
    assert row["id"] is not None
    assert row["subject"] == "Hello"
    assert row["body"] == "Email body"
    assert row["game_name"] == "Notify Game"
