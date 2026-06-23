"""Repository layer: simple data access helpers for application models.

This module implements the SQL needed to persist products, price
history, watches, and notification logs. It keeps SQL statements close
to the schema and returns plain dictionaries (suitable for JSON
serialization) to the calling service layer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.app.database import Database, row_to_dict
from backend.app.domain import ProductSnapshot, SearchResult
from backend.app.money import discount_percent


UNSET = object()


def utc_now_iso() -> str:
    """Return the current datetime as an ISO formatted string (UTC).

    The repository stores all timestamps as ISO strings to simplify
    SQLite usage and to avoid timezone pitfalls.
    """
    return datetime.now(UTC).isoformat()


class Repository:
    """Data access layer for the PS Price application.

    The Repository wraps the `Database` helper and provides convenience
    methods for all application-level entities. Methods return plain
    dictionaries (or lists of dictionaries) so the service and API
    layers can directly return them as JSON without extra mapping.
    """

    def __init__(self, db: Database):
        self.db = db

    def upsert_game_snapshot(
        self, snapshot: ProductSnapshot, *, mark_tracked: bool = True
    ) -> tuple[dict, int | None]:
        """Insert or update a game row and append a price_history entry.

        Args:
            snapshot: A ProductSnapshot describing the current product state.

        Returns:
            A tuple (game_row_dict, previous_price_cents_or_None). The
            returned game row is the current database representation after
            the upsert; `previous_price_cents_or_None` contains the prior
            stored price which is useful for watch evaluation.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM games WHERE product_id = ? AND locale = ?",
                (snapshot.product_id, snapshot.locale),
            ).fetchone()
            previous_price = existing["current_price_cents"] if existing else None
            if existing:
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

    def list_games(self, tracked_only: bool = True) -> list[dict]:
        """Return tracked games with a lightweight column set for fast listing."""
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

    def bulk_mark_tracked(self, game_ids: list[int]) -> list[dict]:
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

    def upsert_catalog_entries(self, entries: list[SearchResult]) -> int:
        """Upsert deal/catalog rows from store listings without user tracking."""
        if not entries:
            return 0
        now = utc_now_iso()
        count = 0
        with self.db._lock, self.db.connect() as conn:
            for entry in entries:
                existing = conn.execute(
                    "SELECT id, is_tracked FROM games WHERE product_id = ? AND locale = ?",
                    (entry.product_id, entry.locale),
                ).fetchone()
                pct = discount_percent(entry.current_price_cents, entry.original_price_cents)
                platforms_json = json.dumps(entry.platforms)
                availability = "available"
                if entry.current_price_cents == 0:
                    availability = "free"
                elif entry.current_price_cents is None:
                    availability = "unknown"

                if existing:
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
                            entry.name,
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
                            existing["id"],
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
                            entry.name,
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
        """Query catalog games with filtering, sorting, and pagination."""
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
        """Search local catalog by name or product id."""
        clean = q.strip()
        if not clean:
            return []
        bounded = max(1, min(limit, 100))
        tokens = [t for t in clean.split() if t]
        with self.db.connect() as conn:
            where_parts: list[str] = []
            params: list[object] = []
            for token in tokens:
                where_parts.append("(name LIKE ? OR product_id LIKE ?)")
                pattern = f"%{token}%"
                params.extend([pattern, pattern])
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
            return [dict(row) for row in rows]

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
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT value FROM catalog_meta WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def catalog_count(self) -> int:
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
        """Return tracked games due for a catalog price refresh."""
        cutoff = datetime.now(UTC) - timedelta(minutes=check_interval_minutes)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, product_id, locale, name, current_price_cents
                FROM games
                WHERE is_tracked = 1
                  AND (last_checked_at IS NULL OR last_checked_at <= ?)
                ORDER BY COALESCE(last_checked_at, created_at)
                """,
                (cutoff.isoformat(),),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_watch(
        self,
        game_id: int,
        email: str,
        target_price_cents: int | None,
        notify_on_any_drop: bool,
        enabled: bool,
        theme_id: str | None = None,
    ) -> dict:
        """Create a new watch for the given game and return the stored row."""
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO watches (
                    game_id, email, target_price_cents, notify_on_any_drop, enabled,
                    theme_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    email,
                    target_price_cents,
                    int(notify_on_any_drop),
                    int(enabled),
                    theme_id,
                    now,
                    now,
                ),
            )
            return dict(conn.execute("SELECT * FROM watches WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def update_watch(
        self,
        watch_id: int,
        target_price_cents: int | None | object = UNSET,
        notify_on_any_drop: bool | None = None,
        enabled: bool | None = None,
    ) -> dict | None:
        """Patch-update a watch row and return the updated row.

        Fields set to their special UNSET sentinel are left unchanged.
        """
        current = self.get_watch(watch_id)
        if not current:
            return None
        new_target = current["target_price_cents"] if target_price_cents is UNSET else target_price_cents
        new_drop = current["notify_on_any_drop"] if notify_on_any_drop is None else int(notify_on_any_drop)
        new_enabled = current["enabled"] if enabled is None else int(enabled)
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE watches
                SET target_price_cents = ?, notify_on_any_drop = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_target, new_drop, new_enabled, now, watch_id),
            )
            return row_to_dict(conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone())

    def get_watch(self, watch_id: int) -> dict | None:
        """Return a single watch row by id or None if missing."""
        with self.db.connect() as conn:
            return row_to_dict(conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone())

    def list_watches(self, game_id: int | None = None, enabled_only: bool = False) -> list[dict]:
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

    def delete_watch(self, watch_id: int) -> bool:
        """Delete a watch by id. Returns True when a row was deleted."""
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
            return cursor.rowcount > 0

    def mark_watch_notified(self, watch_id: int, price_cents: int | None) -> None:
        """Record the last notification price and timestamp for a watch."""
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
                    error, created_at, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (watch_id, game_id, email, subject, body, status, reason, error, now, sent_at),
            )
            return dict(
                conn.execute("SELECT * FROM notifications WHERE id = ?", (cursor.lastrowid,)).fetchone()
            )

    def list_notifications(self, limit: int = 50) -> list[dict]:
        """Return recent notification log entries joined with game name."""
        with self.db.connect() as conn:
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
            return [dict(row) for row in rows]

    def delete_notification(self, notification_id: int) -> bool:
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM notifications WHERE id = ?", (notification_id,)
            )
            return cursor.rowcount > 0

    def delete_notifications(self, notification_ids: list[int]) -> int:
        if not notification_ids:
            return 0
        unique_ids = list(dict.fromkeys(notification_ids))
        with self.db._lock, self.db.connect() as conn:
            placeholders = ",".join("?" * len(unique_ids))
            cursor = conn.execute(
                f"DELETE FROM notifications WHERE id IN ({placeholders})",
                unique_ids,
            )
            return cursor.rowcount


def _hydrate_game_lite(row: dict) -> dict:
    """Lightweight hydration for library list rows."""
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
    """Parse JSON lists and normalize tracked flag on game rows."""
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
    if not values:
        return None
    if isinstance(values, (list, tuple)):
        return json.dumps(list(values))
    return None
