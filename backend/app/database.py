"""Lightweight SQLite database wrapper and migration helper.

**What is SQLite?**

SQLite is a **file-based** relational database — the entire database is one
``.sqlite`` file on disk.  Perfect for small/medium apps: no separate
database server process to install.

**What this module provides**

- ``Database.connect()`` — thread-safe context manager yielding a connection.
- ``Database.migrate()`` — create tables and apply **incremental upgrades**.
- ``row_to_dict()`` — convert ``sqlite3.Row`` objects into plain dicts for
  JSON APIs.

**Migrations (schema evolution)**

When we add a new column (e.g. ``user_id`` on ``watches``), we cannot just
change ``CREATE TABLE`` — existing user databases already have the old
schema.  Migration pattern used here:

1. ``CREATE TABLE IF NOT EXISTS`` — safe on fresh installs.
2. ``PRAGMA table_info(table)`` — list current columns.
3. ``ALTER TABLE ... ADD COLUMN`` — only when the column is missing.

This lets old databases upgrade in place without deleting user data.

**WAL journaling**

``PRAGMA journal_mode = WAL`` (Write-Ahead Logging) lets readers and
writers overlap more safely — important because SMTP runs in threads while
the async server handles HTTP concurrently.

**Foreign keys**

``PRAGMA foreign_keys = ON`` enforces relationships like
``price_history.game_id → games.id``.  SQLite disables this by default!
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
        # RLock = re-entrant lock; same thread can acquire it multiple times.
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
        # timeout=30 waits up to 30s if another connection holds a write lock.
        # check_same_thread=False allows use from asyncio thread pool workers.
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        # Row factory lets us access columns by name: row["name"].
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()  # persist changes when the ``with`` block exits cleanly
        finally:
            conn.close()

    def migrate(self) -> None:
        """Create database schema if it does not exist.

        This method is safe to call multiple times and is executed while
        holding an internal lock to avoid race conditions during startup.
        """
        with self._lock, self.connect() as conn:
            # executescript runs multiple SQL statements in one call.
            conn.executescript(
                """
                -- Core catalog: one row per PS Store product + locale pair.
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

                -- Append-only log of price checks (chart history on game pages).
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

                -- Audit log for every email attempt (sent / failed / skipped).
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
            # Incremental migrations for columns added after initial release.
            self._migrate_games_columns(conn)
            self._migrate_auth_schema(conn)

    def _migrate_auth_schema(self, conn: sqlite3.Connection) -> None:
        """Add user accounts, sessions, and link watches to users.

        ``CREATE TABLE IF NOT EXISTS`` handles brand-new databases.
        The ``PRAGMA table_info`` + ``ALTER TABLE`` blocks below upgrade
        databases that were created before auth columns existed.
        """
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT,
                display_name TEXT,
                email_verified_at TEXT,
                token_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                user_agent TEXT,
                ip_address TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_notification_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                email TEXT NOT NULL COLLATE NOCASE,
                label TEXT,
                verified_at TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, email)
            );
            CREATE INDEX IF NOT EXISTS idx_user_emails_user ON user_notification_emails(user_id);

            CREATE TABLE IF NOT EXISTS passkey_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                credential_id BLOB NOT NULL UNIQUE,
                public_key BLOB NOT NULL,
                sign_count INTEGER NOT NULL DEFAULT 0,
                transports TEXT,
                friendly_name TEXT,
                created_at TEXT NOT NULL,
                last_used_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_passkeys_user ON passkey_credentials(user_id);

            CREATE TABLE IF NOT EXISTS webauthn_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge TEXT NOT NULL UNIQUE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_library (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, game_id)
            );
            CREATE INDEX IF NOT EXISTS idx_user_library_game ON user_library(game_id);
            """
        )
        # --- Column-level migrations on existing tables ---
        watch_cols = {row[1] for row in conn.execute("PRAGMA table_info(watches)")}
        if "user_id" not in watch_cols:
            conn.execute("ALTER TABLE watches ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        if "notification_email_id" not in watch_cols:
            conn.execute(
                "ALTER TABLE watches ADD COLUMN notification_email_id "
                "INTEGER REFERENCES user_notification_emails(id) ON DELETE SET NULL"
            )
        notif_cols = {row[1] for row in conn.execute("PRAGMA table_info(notifications)")}
        if "user_id" not in notif_cols:
            conn.execute(
                "ALTER TABLE notifications ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
            )
        user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "token_version" not in user_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
            )

    def _migrate_games_columns(self, conn: sqlite3.Connection) -> None:
        """Add catalog/deals columns to games when upgrading existing databases.

        Pattern: define desired columns in a dict, compare against
        ``PRAGMA table_info``, run ``ALTER TABLE`` only for missing names.
        """
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
        # Backfill: games created before is_tracked existed should stay tracked.
        if "is_tracked" not in existing:
            conn.execute("UPDATE games SET is_tracked = 1")
        # Indexes speed up common queries (deals page, search, scheduler).
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
        """Add per-watch email theme column when missing."""
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
