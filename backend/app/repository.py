"""Repository layer: SQL-only data access for the PS Price database.

What is the "repository pattern"?
---------------------------------
Instead of sprinkling SQL strings through every part of the app, we collect
*all* database reads and writes in this one module.  Benefits:

- **Single place to learn the schema** — every ``SELECT``, ``INSERT``, and
  ``UPDATE`` for games, watches, and notifications lives here.
- **Service layer stays clean** — ``service.py`` calls ``repo.get_game(...)``
  instead of writing SQL itself.
- **Easy to test** — you can swap a fake repository in unit tests.

Rules this layer follows
------------------------
- **SQL only** — no business rules like "user must own the game".  The service
  layer decides *whether* an operation is allowed; the repository just
  executes it.
- **Return plain dicts** — SQLite rows are converted to Python dictionaries so
  the API can serialize them to JSON without extra mapping classes.

Main tables touched here
------------------------
- ``games`` — catalog entries with current price, metadata, and sync timestamps.
- ``price_history`` — one row appended every time a price is recorded.
- ``user_library`` — which signed-in users track which games.
- ``watches`` — per-user price alert rules (target price, notify-on-drop, etc.).
- ``notifications`` — audit log of emails sent (or attempted).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.app.database import Database, row_to_dict
from backend.app.domain import ProductSnapshot, SearchResult
from backend.app.name_utils import clean_game_name
from backend.app.money import discount_percent


# Sentinel object meaning "caller did not supply this field" in partial updates.
# Compare with ``is UNSET`` instead of ``is None`` because None can be a valid value.
UNSET = object()


def utc_now_iso() -> str:
    """Return the current datetime as an ISO formatted string (UTC).

    The repository stores all timestamps as ISO strings to simplify
    SQLite usage and to avoid timezone pitfalls.
    """
    return datetime.now(UTC).isoformat()


class Repository:
    """Data access layer for the PS Price application.

    The Repository wraps the ``Database`` helper and exposes one method per
    database operation the app needs.  Methods return plain dictionaries (or
    lists of dictionaries) so the service and API layers can return them as
    JSON without extra mapping.

    Thread safety: write methods acquire ``self.db._lock`` before opening a
    connection so concurrent requests do not corrupt SQLite transactions.
    """

    def __init__(self, db: Database):
        self.db = db

    # -------------------------------------------------------------------------
    # Game snapshots and price history
    # -------------------------------------------------------------------------

    def upsert_game_snapshot(
        self, snapshot: ProductSnapshot, *, mark_tracked: bool = True
    ) -> tuple[dict, int | None]:
        """Insert or update a game row and append a price_history entry.

        "Upsert" = UPDATE if the row exists, INSERT if it does not.  We match
        games by ``(product_id, locale)`` because the same title can appear in
        different PlayStation regions.

        Args:
            snapshot: A ProductSnapshot describing the current product state.
            mark_tracked: When inserting a brand-new row, set ``is_tracked=1``.

        Returns:
            A tuple ``(game_row_dict, previous_price_cents_or_None)``.  The
            previous price lets the service layer detect price drops for watch
            evaluation without an extra query.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            # Look up existing row so we know whether to UPDATE or INSERT.
            existing = conn.execute(
                "SELECT * FROM games WHERE product_id = ? AND locale = ?",
                (snapshot.product_id, snapshot.locale),
            ).fetchone()
            previous_price = existing["current_price_cents"] if existing else None
            if existing:
                # Row already in DB — overwrite fields with the fresh snapshot.
                conn.execute(
                    """
                    UPDATE games
                    SET name = ?, category = ?, image_url = ?, store_url = ?, currency = ?,
                        current_price_cents = ?, current_price_formatted = ?,
                        original_price_cents = ?, original_price_formatted = ?,
                        discount_text = ?, availability = ?, price_source = ?,
                        sale_end_at = ?, last_checked_at = ?, last_success_at = ?,
                        last_error = NULL, raw_source_hash = ?, discount_percent = ?,
                        description_short = ?, description_long = ?, publisher = ?, release_date = ?, genres = ?, features = ?,
                        rating_average = ?, rating_count = ?, content_rating = ?,
                        screenshots = ?, edition = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        snapshot.name,
                        snapshot.category,
                        snapshot.image_url,
                        snapshot.store_url,
                        snapshot.currency,
                        snapshot.current_price_cents,
                        snapshot.current_price_formatted,
                        snapshot.original_price_cents,
                        snapshot.original_price_formatted,
                        snapshot.discount_text,
                        snapshot.availability,
                        snapshot.price_source,
                        _dt_iso(snapshot.sale_end_at),
                        _dt_iso(snapshot.fetched_at),
                        _dt_iso(snapshot.fetched_at),
                        snapshot.raw_source_hash,
                        discount_percent(
                            snapshot.current_price_cents, snapshot.original_price_cents
                        ),
                        snapshot.description_short,
                        snapshot.description_long,
                        snapshot.publisher,
                        snapshot.release_date,
                        _json_list(snapshot.genres),
                        _json_list(snapshot.features),
                        snapshot.rating_average,
                        snapshot.rating_count,
                        snapshot.content_rating,
                        _json_list(snapshot.screenshots),
                        snapshot.edition,
                        now,
                        existing["id"],
                    ),
                )
                game_id = existing["id"]
            else:
                # First time we have seen this product — create a new games row.
                cursor = conn.execute(
                    """
                    INSERT INTO games (
                        product_id, locale, name, category, image_url, store_url, currency,
                        current_price_cents, current_price_formatted,
                        original_price_cents, original_price_formatted, discount_text,
                        availability, price_source, sale_end_at, last_checked_at,
                        last_success_at, last_error, raw_source_hash, is_tracked,
                        discount_percent, description_short, description_long, publisher,
                        release_date, genres, features, rating_average, rating_count,
                        content_rating, screenshots, edition, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.product_id,
                        snapshot.locale,
                        snapshot.name,
                        snapshot.category,
                        snapshot.image_url,
                        snapshot.store_url,
                        snapshot.currency,
                        snapshot.current_price_cents,
                        snapshot.current_price_formatted,
                        snapshot.original_price_cents,
                        snapshot.original_price_formatted,
                        snapshot.discount_text,
                        snapshot.availability,
                        snapshot.price_source,
                        _dt_iso(snapshot.sale_end_at),
                        _dt_iso(snapshot.fetched_at),
                        _dt_iso(snapshot.fetched_at),
                        snapshot.raw_source_hash,
                        int(mark_tracked),
                        discount_percent(
                            snapshot.current_price_cents, snapshot.original_price_cents
                        ),
                        snapshot.description_short,
                        snapshot.description_long,
                        snapshot.publisher,
                        snapshot.release_date,
                        _json_list(snapshot.genres),
                        _json_list(snapshot.features),
                        snapshot.rating_average,
                        snapshot.rating_count,
                        snapshot.content_rating,
                        _json_list(snapshot.screenshots),
                        snapshot.edition,
                        now,
                        now,
                    ),
                )
                game_id = cursor.lastrowid

            # Always append a history row so we can chart price over time.
            conn.execute(
                """
                INSERT INTO price_history (
                    game_id, checked_at, price_cents, original_price_cents, currency,
                    price_formatted, original_price_formatted, discount_text, raw_source_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    _dt_iso(snapshot.fetched_at),
                    snapshot.current_price_cents,
                    snapshot.original_price_cents,
                    snapshot.currency,
                    snapshot.current_price_formatted,
                    snapshot.original_price_formatted,
                    snapshot.discount_text,
                    snapshot.raw_source_hash,
                ),
            )
            game = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
            return _hydrate_game(dict(game)), previous_price

    # -------------------------------------------------------------------------
    # Game check status — timestamps and error recording
    # -------------------------------------------------------------------------

    def mark_game_error(self, game_id: int, error: str) -> None:
        """Record a transient error encountered while fetching a game.

        The error message is truncated to avoid unbounded DB field growth.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE games
                SET last_checked_at = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, error[:1000], now, game_id),
            )

    def mark_game_checked(self, game_id: int, checked_at: str | None = None) -> None:
        """Record a successful catalog price check timestamp for a tracked game."""
        now = checked_at or utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE games
                SET last_checked_at = ?, last_success_at = ?, last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, now, now, game_id),
            )

    # -------------------------------------------------------------------------
    # User library — per-user tracked games
    # -------------------------------------------------------------------------

    def list_games(self, tracked_only: bool = True, user_id: int | None = None) -> list[dict]:
        """Return games from a user's library or legacy tracked catalog rows.

        When ``user_id`` is provided, delegates to ``list_games_for_user``.
        Otherwise returns rows where ``is_tracked = 1`` (legacy global tracking).
        """
        if user_id is not None:
            return self.list_games_for_user(user_id)
        clause = "WHERE is_tracked = 1" if tracked_only else ""
        columns = """
            id, product_id, locale, name, image_url, store_url, currency,
            current_price_cents, current_price_formatted, original_price_cents,
            original_price_formatted, discount_text, availability, last_checked_at,
            last_error, discount_percent, is_tracked, created_at, updated_at
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT {columns} FROM games {clause} ORDER BY name COLLATE NOCASE"
            ).fetchall()
            return [_hydrate_game_lite(dict(row)) for row in rows]

    def list_games_for_user(self, user_id: int) -> list[dict]:
        """Return all games in a signed-in user's library via the join table."""
        columns = """
            g.id, g.product_id, g.locale, g.name, g.image_url, g.store_url, g.currency,
            g.current_price_cents, g.current_price_formatted, g.original_price_cents,
            g.original_price_formatted, g.discount_text, g.availability, g.last_checked_at,
            g.last_error, g.discount_percent, g.created_at, g.updated_at
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {columns}
                FROM games g
                JOIN user_library ul ON ul.game_id = g.id
                WHERE ul.user_id = ?
                ORDER BY g.name COLLATE NOCASE
                """,
                (user_id,),
            ).fetchall()
            games = [_hydrate_game_lite(dict(row)) for row in rows]
            for game in games:
                game["is_tracked"] = True
            return games

    def list_all_library_games(self) -> list[dict]:
        """Return minimal game info for every game tracked by any user.

        Used during catalog sync to know which library prices to compare
        before/after the upsert.
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT g.id, g.product_id, g.locale, g.name, g.current_price_cents
                FROM games g
                JOIN user_library ul ON ul.game_id = g.id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def add_user_library(self, user_id: int, game_id: int) -> None:
        """Link a game to a user's library (``INSERT OR IGNORE`` is idempotent)."""
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_library (user_id, game_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, game_id, now),
            )

    def remove_user_library(self, user_id: int, game_id: int) -> bool:
        """Remove a game from a user's library and delete their watches for it."""
        with self.db._lock, self.db.connect() as conn:
            # Watches are per-user; clean them up when the game leaves the library.
            conn.execute(
                "DELETE FROM watches WHERE user_id = ? AND game_id = ?",
                (user_id, game_id),
            )
            cursor = conn.execute(
                "DELETE FROM user_library WHERE user_id = ? AND game_id = ?",
                (user_id, game_id),
            )
            return cursor.rowcount > 0

    def user_has_library_game(self, user_id: int, game_id: int) -> bool:
        """Return True when the user_library join row exists."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM user_library WHERE user_id = ? AND game_id = ?",
                (user_id, game_id),
            ).fetchone()
            return row is not None

    def user_library_ids(self, user_id: int) -> set[int]:
        """Return the set of game IDs in a user's library (for fast membership checks)."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT game_id FROM user_library WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return {row["game_id"] for row in rows}

    def annotate_user_tracked(self, user_id: int | None, games: list[dict]) -> list[dict]:
        """Set ``is_tracked`` on each game dict based on whether the user owns it."""
        if user_id is None:
            return games
        tracked = self.user_library_ids(user_id)
        for game in games:
            game["is_tracked"] = game.get("id") in tracked
        return games

    def bulk_add_user_library(self, user_id: int, game_ids: list[int]) -> list[dict]:
        """Add many games to a user's library and return the hydrated game rows."""
        if not game_ids:
            return []
        now = utc_now_iso()
        unique_ids = list(dict.fromkeys(game_ids))
        with self.db._lock, self.db.connect() as conn:
            for game_id in unique_ids:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO user_library (user_id, game_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, game_id, now),
                )
        return [g for gid in unique_ids if (g := self.get_game(gid))]

        """Mark multiple catalog games as tracked without store calls."""
        if not game_ids:
            return []
        now = utc_now_iso()
        unique_ids = list(dict.fromkeys(game_ids))
        with self.db._lock, self.db.connect() as conn:
            placeholders = ",".join("?" * len(unique_ids))
            conn.execute(
                f"UPDATE games SET is_tracked = 1, updated_at = ? WHERE id IN ({placeholders})",
                (now, *unique_ids),
            )
        return [g for gid in unique_ids if (g := self.get_game(gid))]

    # -------------------------------------------------------------------------
    # Catalog sync and deals browsing
    # -------------------------------------------------------------------------

    def upsert_catalog_entries(self, entries: list[SearchResult]) -> int:
        """Upsert deal/catalog rows from store listings without user tracking.

        Unlike ``upsert_game_snapshot``, new catalog rows get ``is_tracked = 0``
        because merely appearing in the deals feed does not mean a user is
        watching the game.
        """
        if not entries:
            return 0
        now = utc_now_iso()
        count = 0
        with self.db._lock, self.db.connect() as conn:
            for entry in entries:
                existing = conn.execute(
                    "SELECT * FROM games WHERE product_id = ? AND locale = ?",
                    (entry.product_id, entry.locale),
                ).fetchone()
                existing_dict = dict(existing) if existing else None
                pct = discount_percent(entry.current_price_cents, entry.original_price_cents)
                platforms_json = json.dumps(entry.platforms)
                display_name = clean_game_name(entry.name)
                # Derive a simple availability label from the price fields.
                availability = "available"
                if entry.current_price_cents == 0:
                    availability = "free"
                elif entry.current_price_cents is None:
                    availability = "unknown"

                def keep_rich(new_val: object | None, field: str) -> object | None:
                    """Keep scraped detail when GraphQL sync rows omit descriptions."""
                    if new_val:
                        return new_val
                    if existing_dict:
                        return existing_dict.get(field)
                    return None

                description_short = keep_rich(entry.description_short, "description_short")
                description_long = keep_rich(entry.description_long, "description_long")
                publisher = keep_rich(entry.publisher, "publisher")
                release_date = keep_rich(entry.release_date, "release_date")
                edition = keep_rich(entry.edition, "edition")
                genres_json = _json_list(entry.genres) or (
                    existing_dict.get("genres") if existing_dict else None
                )
                features_json = _json_list(entry.features) or (
                    existing_dict.get("features") if existing_dict else None
                )
                screenshots_json = _json_list(entry.screenshots) or (
                    existing_dict.get("screenshots") if existing_dict else None
                )
                rating_average = (
                    entry.rating_average
                    if entry.rating_average is not None
                    else (existing_dict.get("rating_average") if existing_dict else None)
                )
                rating_count = (
                    entry.rating_count
                    if entry.rating_count is not None
                    else (existing_dict.get("rating_count") if existing_dict else None)
                )
                content_rating = keep_rich(entry.content_rating, "content_rating")

                if existing_dict:
                    conn.execute(
                        """
                        UPDATE games
                        SET name = ?, category = ?, image_url = ?, store_url = ?, currency = ?,
                            current_price_cents = ?, current_price_formatted = ?,
                            original_price_cents = ?, original_price_formatted = ?,
                            discount_text = ?, availability = ?, platforms = ?,
                            discount_percent = ?, catalog_synced_at = ?, popularity_rank = ?,
                            description_short = ?, description_long = ?, publisher = ?,
                            release_date = ?, genres = ?, features = ?, rating_average = ?,
                            rating_count = ?, content_rating = ?, screenshots = ?, edition = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            display_name,
                            entry.category,
                            entry.image_url,
                            entry.store_url,
                            entry.currency,
                            entry.current_price_cents,
                            entry.current_price_formatted,
                            entry.original_price_cents,
                            entry.original_price_formatted,
                            entry.discount_text,
                            availability,
                            platforms_json,
                            pct,
                            now,
                            entry.popularity_rank,
                            description_short,
                            description_long,
                            publisher,
                            release_date,
                            genres_json,
                            features_json,
                            rating_average,
                            rating_count,
                            content_rating,
                            screenshots_json,
                            edition,
                            now,
                            existing_dict["id"],
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO games (
                            product_id, locale, name, category, image_url, store_url, currency,
                            current_price_cents, current_price_formatted,
                            original_price_cents, original_price_formatted, discount_text,
                            availability, platforms, discount_percent, is_tracked,
                            catalog_synced_at, popularity_rank, description_short,
                            description_long, publisher, release_date, genres, features,
                            rating_average, rating_count, content_rating, screenshots, edition,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry.product_id,
                            entry.locale,
                            display_name,
                            entry.category,
                            entry.image_url,
                            entry.store_url,
                            entry.currency,
                            entry.current_price_cents,
                            entry.current_price_formatted,
                            entry.original_price_cents,
                            entry.original_price_formatted,
                            entry.discount_text,
                            availability,
                            platforms_json,
                            pct,
                            now,
                            entry.popularity_rank,
                            entry.description_short,
                            entry.description_long,
                            entry.publisher,
                            entry.release_date,
                            _json_list(entry.genres),
                            _json_list(entry.features),
                            entry.rating_average,
                            entry.rating_count,
                            entry.content_rating,
                            _json_list(entry.screenshots),
                            entry.edition,
                            now,
                            now,
                        ),
                    )
                count += 1
        return count

    def list_deals(
        self,
        q: str | None = None,
        platform: str | None = None,
        min_discount: int | None = None,
        max_price_cents: int | None = None,
        on_sale_only: bool = True,
        sort: str = "discount",
        sort_dir: str = "desc",
        limit: int = 48,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Query catalog games with filtering, sorting, and pagination.

        Builds a dynamic SQL ``WHERE`` clause from the optional filters, runs a
        ``COUNT(*)`` for pagination metadata, then returns the page of rows.
        """
        where: list[str] = []
        params: list[object] = []

        if on_sale_only:
            where.append(
                "(discount_percent IS NOT NULL AND discount_percent > 0 "
                "OR original_price_cents IS NOT NULL "
                "AND current_price_cents IS NOT NULL "
                "AND original_price_cents > current_price_cents)"
            )
        if q:
            where.append("name LIKE ?")
            params.append(f"%{q.strip()}%")
        if platform:
            where.append("platforms LIKE ?")
            params.append(f'%"{platform}"%')
        if min_discount is not None and min_discount > 0:
            where.append("discount_percent >= ?")
            params.append(min_discount)
        if max_price_cents is not None:
            where.append("current_price_cents <= ?")
            params.append(max_price_cents)

        suffix = f"WHERE {' AND '.join(where)}" if where else ""
        direction = "ASC" if sort_dir == "asc" else "DESC"
        # Map API sort keys to SQL ORDER BY expressions.
        order_map = {
            "popularity": f"popularity_rank {direction} NULLS LAST, name COLLATE NOCASE",
            "discount": f"discount_percent {direction} NULLS LAST, name COLLATE NOCASE",
            "savings": f"(original_price_cents - current_price_cents) {direction} NULLS LAST",
            "savings_percent": f"discount_percent {direction} NULLS LAST, name COLLATE NOCASE",
            "price": f"current_price_cents {direction} NULLS LAST",
            "original": f"original_price_cents {direction} NULLS LAST",
            "name": f"name COLLATE NOCASE {direction}",
            "newest": f"catalog_synced_at {direction}, updated_at {direction}",
            "rating": f"rating_average {direction} NULLS LAST, rating_count {direction} NULLS LAST",
        }
        order = order_map.get(sort, order_map["discount"])

        with self.db.connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM games {suffix}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT * FROM games {suffix}
                ORDER BY {order}
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
            return [_hydrate_game(dict(row)) for row in rows], total

    def search_catalog(self, q: str, limit: int = 20) -> list[dict]:
        """Search local catalog by name or product id.

        Splits the query into tokens so ``"god war"`` matches titles containing
        both words.  Results prefer prefix matches on the game name.
        """
        clean = q.strip()
        if not clean:
            return []
        bounded = max(1, min(limit, 100))
        tokens = [t for t in clean.split() if t]
        with self.db.connect() as conn:
            where_parts: list[str] = []
            params: list[object] = []
            for token in tokens:
                where_parts.append(
                    "(name LIKE ? OR product_id LIKE ? OR edition LIKE ? OR description_short LIKE ?)"
                )
                pattern = f"%{token}%"
                params.extend([pattern, pattern, pattern, pattern])
            where = " AND ".join(where_parts)
            prefix = f"{clean}%"
            rows = conn.execute(
                f"""
                SELECT * FROM games
                WHERE {where}
                ORDER BY
                    CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                    popularity_rank ASC NULLS LAST,
                    discount_percent DESC NULLS LAST,
                    name COLLATE NOCASE
                LIMIT ?
                """,
                (*params, prefix, bounded),
            ).fetchall()
            return [_hydrate_game(dict(row)) for row in rows]

    def suggest_names(self, q: str, limit: int = 8) -> list[dict]:
        """Return name suggestions for autocomplete from the local catalog."""
        clean = q.strip()
        if not clean:
            return []
        bounded = max(1, min(limit, 20))
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, product_id, image_url, current_price_formatted,
                       discount_percent, is_tracked
                FROM games
                WHERE name LIKE ? OR product_id LIKE ?
                ORDER BY
                    CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                    discount_percent DESC NULLS LAST,
                    name COLLATE NOCASE
                LIMIT ?
                """,
                (f"%{clean}%", f"%{clean}%", f"{clean}%", bounded),
            ).fetchall()
            return [_hydrate_game(dict(row)) for row in rows]

    # -------------------------------------------------------------------------
    # Single-game lookups, history, and scheduler helpers
    # -------------------------------------------------------------------------

    def mark_tracked(self, game_id: int) -> dict | None:
        """Mark a catalog game as actively tracked by the user."""
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                "UPDATE games SET is_tracked = 1, updated_at = ? WHERE id = ?",
                (now, game_id),
            )
            row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
            return _hydrate_game(dict(row)) if row else None

    def set_catalog_meta(self, key: str, value: str) -> None:
        """Store a key/value pair describing catalog sync state (e.g. last sync time)."""
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO catalog_meta (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def get_catalog_meta(self, key: str) -> str | None:
        """Read a single catalog_meta value, or None if the key does not exist."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT value FROM catalog_meta WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def catalog_count(self) -> int:
        """Return total number of rows in the games table."""
        with self.db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    def get_game(self, game_id: int) -> dict | None:
        """Return a single game row by its integer id or None if missing."""
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
            return _hydrate_game(dict(row)) if row else None

    def get_game_by_product(self, product_id: str, locale: str) -> dict | None:
        """Lookup a game by product_id and locale pair."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM games WHERE product_id = ? AND locale = ?",
                (product_id, locale),
            ).fetchone()
            return _hydrate_game(dict(row)) if row else None

    def delete_game(self, game_id: int) -> bool:
        """Delete a game and cascade-delete related watches/history.

        Returns True when a row was deleted.
        """
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
            return cursor.rowcount > 0

    def get_history(self, game_id: int, limit: int = 50) -> list[dict]:
        """Return the most recent price history rows for a game."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM price_history
                WHERE game_id = ?
                ORDER BY checked_at DESC, id DESC
                LIMIT ?
                """,
                (game_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def due_games(self, check_interval_minutes: int) -> list[dict]:
        """Return library games due for a catalog price refresh.

        A game is "due" when ``last_checked_at`` is NULL or older than the
        configured interval.  The background scheduler uses this to decide when
        to call ``sync_deals``.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=check_interval_minutes)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT g.id, g.product_id, g.locale, g.name, g.current_price_cents
                FROM games g
                JOIN user_library ul ON ul.game_id = g.id
                WHERE g.last_checked_at IS NULL OR g.last_checked_at <= ?
                ORDER BY COALESCE(g.last_checked_at, g.created_at)
                """,
                (cutoff.isoformat(),),
            ).fetchall()
            return [dict(row) for row in rows]

    # -------------------------------------------------------------------------
    # Watches — per-user price alert rules
    # -------------------------------------------------------------------------

    def create_watch(
        self,
        game_id: int,
        email: str,
        target_price_cents: int | None,
        notify_on_any_drop: bool,
        enabled: bool,
        theme_id: str | None = None,
        *,
        user_id: int | None = None,
        notification_email_id: int | None = None,
        min_drop_cents: int | None = None,
        min_drop_percent: int | None = None,
    ) -> dict:
        """Create a new watch for the given game and return the stored row.

        A watch stores *what* to notify about (target price, any-drop flag) and
        *where* to send it (email, optional theme).  Business validation
        (library membership, verified email) happens in the service layer.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO watches (
                    game_id, email, target_price_cents, notify_on_any_drop, enabled,
                    theme_id, user_id, notification_email_id, min_drop_cents, min_drop_percent,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    email,
                    target_price_cents,
                    int(notify_on_any_drop),
                    int(enabled),
                    theme_id,
                    user_id,
                    notification_email_id,
                    min_drop_cents,
                    min_drop_percent,
                    now,
                    now,
                ),
            )
            return dict(conn.execute("SELECT * FROM watches WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def get_watch(self, watch_id: int, user_id: int | None = None) -> dict | None:
        """Return a single watch row by id or None if missing."""
        with self.db.connect() as conn:
            if user_id is None:
                return row_to_dict(conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone())
            return row_to_dict(
                conn.execute(
                    "SELECT * FROM watches WHERE id = ? AND user_id = ?",
                    (watch_id, user_id),
                ).fetchone()
            )

    def update_watch(
        self,
        watch_id: int,
        target_price_cents: int | None | object = UNSET,
        notify_on_any_drop: bool | None = None,
        enabled: bool | None = None,
        min_drop_cents: int | None | object = UNSET,
        min_drop_percent: int | None | object = UNSET,
        notification_email_id: int | None | object = UNSET,
        email: str | None | object = UNSET,
    ) -> dict | None:
        """Patch-update a watch row and return the updated row.

        Fields set to the special ``UNSET`` sentinel are left unchanged.  This
        lets the API send partial updates (e.g. only toggle ``enabled``) without
        overwriting other columns with ``None``.
        """
        current = self.get_watch(watch_id)
        if not current:
            return None
        new_target = current["target_price_cents"] if target_price_cents is UNSET else target_price_cents
        new_drop = current["notify_on_any_drop"] if notify_on_any_drop is None else int(notify_on_any_drop)
        new_enabled = current["enabled"] if enabled is None else int(enabled)
        new_min_cents = current.get("min_drop_cents") if min_drop_cents is UNSET else min_drop_cents
        new_min_pct = current.get("min_drop_percent") if min_drop_percent is UNSET else min_drop_percent
        new_email_id = (
            current.get("notification_email_id")
            if notification_email_id is UNSET
            else notification_email_id
        )
        new_email = current["email"] if email is UNSET else email
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE watches
                SET target_price_cents = ?, notify_on_any_drop = ?, enabled = ?,
                    min_drop_cents = ?, min_drop_percent = ?, notification_email_id = ?,
                    email = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_target,
                    new_drop,
                    new_enabled,
                    new_min_cents,
                    new_min_pct,
                    new_email_id,
                    new_email,
                    now,
                    watch_id,
                ),
            )
            return row_to_dict(conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone())

    def list_watches(
        self,
        game_id: int | None = None,
        enabled_only: bool = False,
        user_id: int | None = None,
    ) -> list[dict]:
        """List watches optionally filtered by game_id and enabled state.

        The returned rows include some selected game columns for convenience
        in the API layer (game_name, current_price_cents, etc.).
        """
        where: list[str] = []
        params: list[object] = []
        if game_id is not None:
            where.append("w.game_id = ?")
            params.append(game_id)
        if enabled_only:
            where.append("w.enabled = 1")
        if user_id is not None:
            where.append("w.user_id = ?")
            params.append(user_id)
        suffix = f"WHERE {' AND '.join(where)}" if where else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.*, g.name AS game_name, g.current_price_cents, g.current_price_formatted,
                       g.currency, g.store_url
                FROM watches w
                JOIN games g ON g.id = w.game_id
                {suffix}
                ORDER BY w.created_at DESC
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_watch(self, watch_id: int, user_id: int | None = None) -> bool:
        """Delete a watch by id. Returns True when a row was deleted."""
        with self.db._lock, self.db.connect() as conn:
            if user_id is None:
                cursor = conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
            else:
                cursor = conn.execute(
                    "DELETE FROM watches WHERE id = ? AND user_id = ?",
                    (watch_id, user_id),
                )
            return cursor.rowcount > 0

    def mark_watch_notified(self, watch_id: int, price_cents: int | None) -> None:
        """Record the last notification price and timestamp for a watch.

        The service layer consults these fields to avoid sending duplicate
        emails when the price has not dropped further since the last alert.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE watches
                SET last_notified_price_cents = ?, last_notified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (price_cents, now, now, watch_id),
            )

    # -------------------------------------------------------------------------
    # Notifications — email audit log
    # -------------------------------------------------------------------------

    def log_notification(
        self,
        watch_id: int | None,
        game_id: int | None,
        email: str,
        subject: str,
        body: str,
        status: str,
        reason: str | None,
        error: str | None = None,
        user_id: int | None = None,
    ) -> dict:
        """Insert a notification record and return the new row.

        `status` is expected to be one of: "pending", "sent", "failed".
        """
        now = utc_now_iso()
        sent_at = now if status == "sent" else None
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notifications (
                    watch_id, game_id, email, subject, body, status, reason,
                    error, created_at, sent_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (watch_id, game_id, email, subject, body, status, reason, error, now, sent_at, user_id),
            )
            return dict(
                conn.execute("SELECT * FROM notifications WHERE id = ?", (cursor.lastrowid,)).fetchone()
            )

    def list_notifications(self, limit: int = 50, user_id: int | None = None) -> list[dict]:
        """Return recent notification log entries joined with game name."""
        with self.db.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT n.*, g.name AS game_name
                    FROM notifications n
                    LEFT JOIN games g ON g.id = n.game_id
                    ORDER BY n.created_at DESC, n.id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT n.*, g.name AS game_name
                    FROM notifications n
                    LEFT JOIN games g ON g.id = n.game_id
                    WHERE n.user_id = ? AND COALESCE(n.reason, '') != 'system'
                    ORDER BY n.created_at DESC, n.id DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            return [dict(row) for row in rows]

    def delete_notification(self, notification_id: int, user_id: int | None = None) -> bool:
        """Delete one notification log row. Returns True when a row was deleted."""
        with self.db._lock, self.db.connect() as conn:
            if user_id is None:
                cursor = conn.execute(
                    "DELETE FROM notifications WHERE id = ?", (notification_id,)
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM notifications WHERE id = ? AND user_id = ?",
                    (notification_id, user_id),
                )
            return cursor.rowcount > 0

    def delete_notifications(self, notification_ids: list[int], user_id: int | None = None) -> int:
        """Delete many notification rows at once. Returns the number deleted."""
        if not notification_ids:
            return 0
        unique_ids = list(dict.fromkeys(notification_ids))
        with self.db._lock, self.db.connect() as conn:
            placeholders = ",".join("?" * len(unique_ids))
            if user_id is None:
                cursor = conn.execute(
                    f"DELETE FROM notifications WHERE id IN ({placeholders})",
                    unique_ids,
                )
            else:
                cursor = conn.execute(
                    f"DELETE FROM notifications WHERE id IN ({placeholders}) AND user_id = ?",
                    (*unique_ids, user_id),
                )
            return cursor.rowcount


# -----------------------------------------------------------------------------
# Module-level helpers — row hydration and serialization
# -----------------------------------------------------------------------------

def _hydrate_game_lite(row: dict) -> dict:
    """Lightweight hydration for library list rows.

    List endpoints skip parsing heavy JSON columns (platforms, screenshots)
    and instead return empty lists for those fields to keep responses fast.
    """
    row["platforms"] = []
    row["genres"] = []
    row["features"] = []
    row["screenshots"] = []
    row["is_tracked"] = bool(row.get("is_tracked"))
    if row.get("original_price_cents") is not None and row.get("current_price_cents") is not None:
        row["savings_cents"] = max(0, row["original_price_cents"] - row["current_price_cents"])
    else:
        row["savings_cents"] = None
    return row


def _dt_iso(value: datetime | None) -> str | None:
    """Convert an optional datetime to ISO string or return None."""
    return value.isoformat() if value else None


def _hydrate_game(row: dict) -> dict:
    """Parse JSON list columns and normalize the tracked flag on full game rows.

    SQLite stores list fields (genres, screenshots, etc.) as JSON text.
    This helper converts them back to Python lists for the API.
    """
    platforms = row.get("platforms")
    if isinstance(platforms, str) and platforms:
        try:
            row["platforms"] = json.loads(platforms)
        except json.JSONDecodeError:
            row["platforms"] = []
    elif platforms is None:
        row["platforms"] = []
    for field in ("genres", "features", "screenshots"):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                row[field] = json.loads(value)
            except json.JSONDecodeError:
                row[field] = []
        elif value is None:
            row[field] = []
    row["is_tracked"] = bool(row.get("is_tracked"))
    if row.get("original_price_cents") is not None and row.get("current_price_cents") is not None:
        row["savings_cents"] = max(0, row["original_price_cents"] - row["current_price_cents"])
    else:
        row["savings_cents"] = None
    return row


def _json_list(values: object) -> str | None:
    """Serialize a Python list to a JSON string for SQLite storage, or None."""
    if not values:
        return None
    if isinstance(values, (list, tuple)):
        return json.dumps(list(values))
    return None
