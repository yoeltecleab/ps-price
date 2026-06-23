"""Lightweight SQLite database wrapper and migration helper.

This module provides a minimal `Database` class that is intentionally
simple: it exposes a thread-safe context manager for obtaining a
sqlite3.Connection and a `migrate()` method used on application startup
to ensure the schema exists. The schema contains four tables used by
the application: `games`, `price_history`, `watches`, and `notifications`.

The module also exposes `row_to_dict` to convert sqlite3.Row objects to
plain dictionaries which simplifies repository code.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    """Simple thread-safe SQLite helper.

    The Database class is intentionally minimal: use `connect()` as a
    context manager to get a `sqlite3.Connection`. The connection is
    configured with foreign keys and WAL journaling for better
    concurrency. `migrate()` will create necessary tables when the
    application starts.

    Example:
        db = Database(settings.database_path)
        db.migrate()
        with db.connect() as conn:
            conn.execute(...)
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.RLock()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager that yields a configured sqlite3.Connection.

        The method ensures the parent directory exists, configures a
        Row factory and pragmas, and commits/ closes the connection on
        exit. `check_same_thread=False` is used because this app uses a
        thread-based executor for some IO paths (e.g. SMTP).
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def migrate(self) -> None:
        """Create database schema if it does not exist.

        This method is safe to call multiple times and is executed while
        holding an internal lock to avoid race conditions during startup.
        """
        with self._lock, self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT,
                    image_url TEXT,
                    store_url TEXT NOT NULL,
                    currency TEXT,
                    current_price_cents INTEGER,
                    current_price_formatted TEXT,
                    original_price_cents INTEGER,
                    original_price_formatted TEXT,
                    discount_text TEXT,
                    availability TEXT NOT NULL DEFAULT 'unknown',
                    price_source TEXT,
                    sale_end_at TEXT,
                    last_checked_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT,
                    raw_source_hash TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(product_id, locale)
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                    checked_at TEXT NOT NULL,
                    price_cents INTEGER,
                    original_price_cents INTEGER,
                    currency TEXT,
                    price_formatted TEXT,
                    original_price_formatted TEXT,
                    discount_text TEXT,
                    raw_source_hash TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_price_history_game_checked
                    ON price_history(game_id, checked_at DESC);

                CREATE TABLE IF NOT EXISTS watches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    target_price_cents INTEGER,
                    notify_on_any_drop INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_notified_price_cents INTEGER,
                    last_notified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_watches_game_enabled
                    ON watches(game_id, enabled);

                CREATE TABLE IF NOT EXISTS catalog_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    watch_id INTEGER REFERENCES watches(id) ON DELETE SET NULL,
                    game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );
                """
            )
            self._migrate_games_columns(conn)

    def _migrate_games_columns(self, conn: sqlite3.Connection) -> None:
        """Add catalog/deals columns to games when upgrading existing databases."""
        columns = {
            "platforms": "TEXT",
            "discount_percent": "INTEGER",
            "is_tracked": "INTEGER NOT NULL DEFAULT 0",
            "catalog_synced_at": "TEXT",
            "description_short": "TEXT",
            "description_long": "TEXT",
            "publisher": "TEXT",
            "release_date": "TEXT",
            "genres": "TEXT",
            "features": "TEXT",
            "rating_average": "REAL",
            "rating_count": "INTEGER",
            "content_rating": "TEXT",
            "screenshots": "TEXT",
            "edition": "TEXT",
            "popularity_rank": "INTEGER",
        }
        existing = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE games ADD COLUMN {name} {definition}")
        if "is_tracked" not in existing:
            conn.execute("UPDATE games SET is_tracked = 1")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_discount ON games(discount_percent DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_name ON games(name COLLATE NOCASE)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_popularity ON games(popularity_rank ASC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_tracked_checked "
            "ON games(is_tracked, last_checked_at)"
        )
        self._migrate_watch_columns(conn)

    def _migrate_watch_columns(self, conn: sqlite3.Connection) -> None:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(watches)")}
        if "theme_id" not in existing:
            conn.execute("ALTER TABLE watches ADD COLUMN theme_id TEXT")


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a sqlite3.Row to a plain dict or return None.

    This helper simplifies repository code that needs to return JSON
    serializable dictionaries from database rows.
    """
    if row is None:
        return None
    return dict(row)
