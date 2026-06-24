"""Schema creation and incremental migrations for SQLite and PostgreSQL."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.db.connection import Database, DbConnection


def run_migrations(db: Database) -> None:
    """Create tables and apply incremental upgrades."""
    with db._lock, db.connect() as conn:
        if db.dialect == "postgresql":
            _bootstrap_postgres(conn)
            _migrate_postgres_columns(conn)
        else:
            _bootstrap_sqlite(conn)
            _migrate_games_columns(conn, "sqlite")
            _migrate_auth_schema(conn, "sqlite")


def row_to_dict(row) -> dict | None:
    """Convert a database row to a plain dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "_asdict"):
        return row._asdict()
    return dict(row)


def _column_names(conn: DbConnection, table: str, dialect: str) -> set[str]:
    if dialect == "sqlite":
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    ).fetchall()
    names: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            names.add(row["column_name"])
        else:
            names.add(row[0])
    return names


def _bootstrap_sqlite(conn: DbConnection) -> None:
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
    _migrate_auth_schema(conn, "sqlite")


def _migrate_auth_schema(conn: DbConnection, dialect: str) -> None:
    if dialect == "sqlite":
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT,
                display_name TEXT,
                email_verified_at TEXT,
                token_version INTEGER NOT NULL DEFAULT 0,
                preferred_theme_id TEXT,
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

    watch_cols = _column_names(conn, "watches", dialect)
    if "user_id" not in watch_cols:
        conn.execute(
            "ALTER TABLE watches ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
        )
    if "notification_email_id" not in watch_cols:
        conn.execute(
            "ALTER TABLE watches ADD COLUMN notification_email_id "
            "INTEGER REFERENCES user_notification_emails(id) ON DELETE SET NULL"
        )

    notif_cols = _column_names(conn, "notifications", dialect)
    if "user_id" not in notif_cols:
        conn.execute(
            "ALTER TABLE notifications ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
        )

    user_cols = _column_names(conn, "users", dialect)
    if "token_version" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")
    if "preferred_theme_id" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN preferred_theme_id TEXT")


def _migrate_games_columns(conn: DbConnection, dialect: str) -> None:
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
    existing = _column_names(conn, "games", dialect)
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE games ADD COLUMN {name} {definition}")
    if "is_tracked" not in existing:
        conn.execute("UPDATE games SET is_tracked = 1")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_games_discount ON games(discount_percent DESC)"
    )
    if dialect == "sqlite":
        conn.execute("CREATE INDEX IF NOT EXISTS idx_games_name ON games(name COLLATE NOCASE)")
    else:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_games_name ON games (LOWER(name))")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_games_popularity ON games(popularity_rank ASC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_games_tracked_checked ON games(is_tracked, last_checked_at)"
    )
    _migrate_watch_columns(conn, dialect)


def _migrate_watch_columns(conn: DbConnection, dialect: str) -> None:
    existing = _column_names(conn, "watches", dialect)
    if "theme_id" not in existing:
        conn.execute("ALTER TABLE watches ADD COLUMN theme_id TEXT")
    if "min_drop_cents" not in existing:
        conn.execute("ALTER TABLE watches ADD COLUMN min_drop_cents INTEGER")
    if "min_drop_percent" not in existing:
        conn.execute("ALTER TABLE watches ADD COLUMN min_drop_percent INTEGER")


def _bootstrap_postgres(conn: DbConnection) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS citext")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
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
            platforms TEXT,
            discount_percent INTEGER,
            is_tracked INTEGER NOT NULL DEFAULT 0,
            catalog_synced_at TEXT,
            description_short TEXT,
            description_long TEXT,
            publisher TEXT,
            release_date TEXT,
            genres TEXT,
            features TEXT,
            rating_average DOUBLE PRECISION,
            rating_count INTEGER,
            content_rating TEXT,
            screenshots TEXT,
            edition TEXT,
            popularity_rank INTEGER,
            UNIQUE(product_id, locale)
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
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

        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email CITEXT NOT NULL UNIQUE,
            password_hash TEXT,
            display_name TEXT,
            email_verified_at TEXT,
            token_version INTEGER NOT NULL DEFAULT 0,
            preferred_theme_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_notification_emails (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            email CITEXT NOT NULL,
            label TEXT,
            verified_at TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, email)
        );
        CREATE INDEX IF NOT EXISTS idx_user_emails_user ON user_notification_emails(user_id);

        CREATE TABLE IF NOT EXISTS watches (
            id SERIAL PRIMARY KEY,
            game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            target_price_cents INTEGER,
            notify_on_any_drop INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_notified_price_cents INTEGER,
            last_notified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            notification_email_id INTEGER REFERENCES user_notification_emails(id) ON DELETE SET NULL,
            theme_id TEXT,
            min_drop_cents INTEGER,
            min_drop_percent INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_watches_game_enabled ON watches(game_id, enabled);

        CREATE TABLE IF NOT EXISTS catalog_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            watch_id INTEGER REFERENCES watches(id) ON DELETE SET NULL,
            game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            user_agent TEXT,
            ip_address TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

        CREATE TABLE IF NOT EXISTS email_verification_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS passkey_credentials (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            credential_id BYTEA NOT NULL UNIQUE,
            public_key BYTEA NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            transports TEXT,
            friendly_name TEXT,
            created_at TEXT NOT NULL,
            last_used_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_passkeys_user ON passkey_credentials(user_id);

        CREATE TABLE IF NOT EXISTS webauthn_challenges (
            id SERIAL PRIMARY KEY,
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

        CREATE INDEX IF NOT EXISTS idx_games_discount ON games(discount_percent DESC);
        CREATE INDEX IF NOT EXISTS idx_games_name ON games (LOWER(name));
        CREATE INDEX IF NOT EXISTS idx_games_popularity ON games(popularity_rank ASC);
        CREATE INDEX IF NOT EXISTS idx_games_tracked_checked ON games(is_tracked, last_checked_at);
        """
    )


def _migrate_postgres_columns(conn: DbConnection) -> None:
    """Incremental upgrades for PostgreSQL databases created before new columns."""
    _migrate_games_columns(conn, "postgresql")
    _migrate_auth_schema(conn, "postgresql")
    _migrate_watch_columns(conn, "postgresql")
