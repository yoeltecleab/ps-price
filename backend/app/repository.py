"""Repository layer: ORM data access for the PS Price database.

What is the "repository pattern"?
---------------------------------
Instead of sprinkling SQL strings through every part of the app, we collect
*all* database reads and writes in this one module.  Benefits:

- **Single place to learn the schema** — every query for games, watches, and
  notifications lives here.
- **Service layer stays clean** — ``service.py`` calls ``repo.get_game(...)``
  instead of writing queries itself.
- **Easy to test** — you can swap a fake repository in unit tests.

Rules this layer follows
------------------------
- **Data access only** — no business rules like "user must own the game".  The
  service layer decides *whether* an operation is allowed; the repository just
  executes it.
- **Return plain dicts** — ORM rows are converted to Python dictionaries so
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

from sqlalchemy import and_, case, delete, distinct, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.app.database import Database, row_to_dict
from backend.app.db.models import (
    CatalogMeta,
    Game,
    Notification,
    PriceHistory,
    User,
    UserLibrary,
    UserNotificationEmail,
    Watch,
)
from backend.app.db.util import as_dict, utc_now_iso
from backend.app.domain import ProductSnapshot, SearchResult
from backend.app.money import discount_percent
from backend.app.name_utils import clean_game_name


# Sentinel object meaning "caller did not supply this field" in partial updates.
# Compare with ``is UNSET`` instead of ``is None`` because None can be a valid value.
UNSET = object()


class Repository:
    """Data access layer for the PS Price application.

    The Repository wraps the ``Database`` helper and exposes one method per
    database operation the app needs.  Methods return plain dictionaries (or
    lists of dictionaries) so the service and API layers can return them as
    JSON without extra mapping.

    Thread safety: ``Database.session()`` acquires the DB lock and commits or
    rolls back each unit of work.
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
        pct = discount_percent(snapshot.current_price_cents, snapshot.original_price_cents)
        with self.db.session() as session:
            existing = session.scalar(
                select(Game).where(
                    Game.product_id == snapshot.product_id,
                    Game.locale == snapshot.locale,
                )
            )
            previous_price = existing.current_price_cents if existing else None
            if existing:
                existing.name = snapshot.name
                existing.category = snapshot.category
                existing.image_url = snapshot.image_url
                existing.store_url = snapshot.store_url
                existing.currency = snapshot.currency
                existing.current_price_cents = snapshot.current_price_cents
                existing.current_price_formatted = snapshot.current_price_formatted
                existing.original_price_cents = snapshot.original_price_cents
                existing.original_price_formatted = snapshot.original_price_formatted
                existing.discount_text = snapshot.discount_text
                existing.availability = snapshot.availability
                existing.price_source = snapshot.price_source
                existing.sale_end_at = _dt_iso(snapshot.sale_end_at)
                existing.last_checked_at = _dt_iso(snapshot.fetched_at)
                existing.last_success_at = _dt_iso(snapshot.fetched_at)
                existing.last_error = None
                existing.raw_source_hash = snapshot.raw_source_hash
                existing.discount_percent = pct
                existing.description_short = snapshot.description_short
                existing.description_long = snapshot.description_long
                existing.publisher = snapshot.publisher
                existing.release_date = snapshot.release_date
                existing.genres = _json_list(snapshot.genres)
                existing.features = _json_list(snapshot.features)
                existing.rating_average = snapshot.rating_average
                existing.rating_count = snapshot.rating_count
                existing.content_rating = snapshot.content_rating
                existing.screenshots = _json_list(snapshot.screenshots)
                existing.edition = snapshot.edition
                existing.updated_at = now
                game_id = existing.id
            else:
                game = Game(
                    product_id=snapshot.product_id,
                    locale=snapshot.locale,
                    name=snapshot.name,
                    category=snapshot.category,
                    image_url=snapshot.image_url,
                    store_url=snapshot.store_url,
                    currency=snapshot.currency,
                    current_price_cents=snapshot.current_price_cents,
                    current_price_formatted=snapshot.current_price_formatted,
                    original_price_cents=snapshot.original_price_cents,
                    original_price_formatted=snapshot.original_price_formatted,
                    discount_text=snapshot.discount_text,
                    availability=snapshot.availability,
                    price_source=snapshot.price_source,
                    sale_end_at=_dt_iso(snapshot.sale_end_at),
                    last_checked_at=_dt_iso(snapshot.fetched_at),
                    last_success_at=_dt_iso(snapshot.fetched_at),
                    last_error=None,
                    raw_source_hash=snapshot.raw_source_hash,
                    is_tracked=int(mark_tracked),
                    discount_percent=pct,
                    description_short=snapshot.description_short,
                    description_long=snapshot.description_long,
                    publisher=snapshot.publisher,
                    release_date=snapshot.release_date,
                    genres=_json_list(snapshot.genres),
                    features=_json_list(snapshot.features),
                    rating_average=snapshot.rating_average,
                    rating_count=snapshot.rating_count,
                    content_rating=snapshot.content_rating,
                    screenshots=_json_list(snapshot.screenshots),
                    edition=snapshot.edition,
                    created_at=now,
                    updated_at=now,
                )
                session.add(game)
                session.flush()
                game_id = game.id

            session.add(
                PriceHistory(
                    game_id=game_id,
                    checked_at=_dt_iso(snapshot.fetched_at),
                    price_cents=snapshot.current_price_cents,
                    original_price_cents=snapshot.original_price_cents,
                    currency=snapshot.currency,
                    price_formatted=snapshot.current_price_formatted,
                    original_price_formatted=snapshot.original_price_formatted,
                    discount_text=snapshot.discount_text,
                    raw_source_hash=snapshot.raw_source_hash,
                )
            )
            game_row = session.get(Game, game_id)
            return _hydrate_game(as_dict(game_row)), previous_price

    # -------------------------------------------------------------------------
    # Game check status — timestamps and error recording
    # -------------------------------------------------------------------------

    def mark_game_error(self, game_id: int, error: str) -> None:
        """Record a transient error encountered while fetching a game.

        The error message is truncated to avoid unbounded DB field growth.
        """
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(Game)
                .where(Game.id == game_id)
                .values(last_checked_at=now, last_error=error[:1000], updated_at=now)
            )

    def mark_game_checked(self, game_id: int, checked_at: str | None = None) -> None:
        """Record a successful catalog price check timestamp for a tracked game."""
        now = checked_at or utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(Game)
                .where(Game.id == game_id)
                .values(
                    last_checked_at=now,
                    last_success_at=now,
                    last_error=None,
                    updated_at=now,
                )
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
        stmt = _game_lite_select().order_by(func.lower(Game.name))
        if tracked_only:
            stmt = stmt.where(Game.is_tracked == 1)
        with self.db.session() as session:
            rows = session.execute(stmt).mappings().all()
            return [_hydrate_game_lite(dict(row)) for row in rows]

    def list_games_for_user(self, user_id: int) -> list[dict]:
        """Return all games in a signed-in user's library via the join table."""
        stmt = (
            _game_lite_select(exclude_is_tracked=True)
            .join(UserLibrary, UserLibrary.game_id == Game.id)
            .where(UserLibrary.user_id == user_id)
            .order_by(func.lower(Game.name))
        )
        with self.db.session() as session:
            rows = session.execute(stmt).mappings().all()
            games = [_hydrate_game_lite(dict(row)) for row in rows]
            for game in games:
                game["is_tracked"] = True
            return games

    def list_all_library_games(self) -> list[dict]:
        """Return minimal game info for every game tracked by any user.

        Used during catalog sync to know which library prices to compare
        before/after the upsert.
        """
        stmt = (
            select(
                Game.id,
                Game.product_id,
                Game.locale,
                Game.name,
                Game.current_price_cents,
            )
            .join(UserLibrary, UserLibrary.game_id == Game.id)
            .distinct()
        )
        with self.db.session() as session:
            rows = session.execute(stmt).mappings().all()
            return [dict(row) for row in rows]

    def add_user_library(self, user_id: int, game_id: int) -> None:
        """Link a game to a user's library (idempotent insert)."""
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                pg_insert(UserLibrary)
                .values(user_id=user_id, game_id=game_id, created_at=now)
                .on_conflict_do_nothing()
            )

    def remove_user_library(self, user_id: int, game_id: int) -> bool:
        """Remove a game from a user's library and delete their watches for it."""
        with self.db.session() as session:
            session.execute(
                delete(Watch).where(Watch.user_id == user_id, Watch.game_id == game_id)
            )
            result = session.execute(
                delete(UserLibrary).where(
                    UserLibrary.user_id == user_id,
                    UserLibrary.game_id == game_id,
                )
            )
            return result.rowcount > 0

    def user_has_library_game(self, user_id: int, game_id: int) -> bool:
        """Return True when the user_library join row exists."""
        with self.db.session() as session:
            return (
                session.scalar(
                    select(UserLibrary.game_id).where(
                        UserLibrary.user_id == user_id,
                        UserLibrary.game_id == game_id,
                    )
                )
                is not None
            )

    def user_library_ids(self, user_id: int) -> set[int]:
        """Return the set of game IDs in a user's library (for fast membership checks)."""
        with self.db.session() as session:
            rows = session.scalars(
                select(UserLibrary.game_id).where(UserLibrary.user_id == user_id)
            ).all()
            return set(rows)

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
        with self.db.session() as session:
            session.execute(
                pg_insert(UserLibrary)
                .values(
                    [
                        {"user_id": user_id, "game_id": game_id, "created_at": now}
                        for game_id in unique_ids
                    ]
                )
                .on_conflict_do_nothing()
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
        with self.db.session() as session:
            for entry in entries:
                existing = session.scalar(
                    select(Game).where(
                        Game.product_id == entry.product_id,
                        Game.locale == entry.locale,
                    )
                )
                existing_dict = as_dict(existing)
                pct = discount_percent(entry.current_price_cents, entry.original_price_cents)
                platforms_json = json.dumps(entry.platforms)
                display_name = clean_game_name(entry.name)
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

                if existing:
                    existing.name = display_name
                    existing.category = entry.category
                    existing.image_url = entry.image_url
                    existing.store_url = entry.store_url
                    existing.currency = entry.currency
                    existing.current_price_cents = entry.current_price_cents
                    existing.current_price_formatted = entry.current_price_formatted
                    existing.original_price_cents = entry.original_price_cents
                    existing.original_price_formatted = entry.original_price_formatted
                    existing.discount_text = entry.discount_text
                    existing.availability = availability
                    existing.platforms = platforms_json
                    existing.discount_percent = pct
                    existing.catalog_synced_at = now
                    existing.popularity_rank = entry.popularity_rank
                    existing.description_short = description_short
                    existing.description_long = description_long
                    existing.publisher = publisher
                    existing.release_date = release_date
                    existing.genres = genres_json
                    existing.features = features_json
                    existing.rating_average = rating_average
                    existing.rating_count = rating_count
                    existing.content_rating = content_rating
                    existing.screenshots = screenshots_json
                    existing.edition = edition
                    existing.updated_at = now
                else:
                    session.add(
                        Game(
                            product_id=entry.product_id,
                            locale=entry.locale,
                            name=display_name,
                            category=entry.category,
                            image_url=entry.image_url,
                            store_url=entry.store_url,
                            currency=entry.currency,
                            current_price_cents=entry.current_price_cents,
                            current_price_formatted=entry.current_price_formatted,
                            original_price_cents=entry.original_price_cents,
                            original_price_formatted=entry.original_price_formatted,
                            discount_text=entry.discount_text,
                            availability=availability,
                            platforms=platforms_json,
                            discount_percent=pct,
                            is_tracked=0,
                            catalog_synced_at=now,
                            popularity_rank=entry.popularity_rank,
                            description_short=entry.description_short,
                            description_long=entry.description_long,
                            publisher=entry.publisher,
                            release_date=entry.release_date,
                            genres=_json_list(entry.genres),
                            features=_json_list(entry.features),
                            rating_average=entry.rating_average,
                            rating_count=entry.rating_count,
                            content_rating=entry.content_rating,
                            screenshots=_json_list(entry.screenshots),
                            edition=entry.edition,
                            created_at=now,
                            updated_at=now,
                        )
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

        Builds dynamic SQLAlchemy filters from the optional parameters, runs a
        count for pagination metadata, then returns the page of rows.
        """
        filters = _deals_filters(
            q=q,
            platform=platform,
            min_discount=min_discount,
            max_price_cents=max_price_cents,
            on_sale_only=on_sale_only,
        )
        order = _deals_order_by(sort, sort_dir)

        with self.db.session() as session:
            count_stmt = select(func.count()).select_from(Game)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = session.scalar(count_stmt) or 0

            stmt = select(Game)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(*order).limit(limit).offset(offset)
            rows = session.scalars(stmt).all()
            return [_hydrate_game(as_dict(row)) for row in rows], total

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
        token_filters = []
        for token in tokens:
            pattern = f"%{token}%"
            token_filters.append(
                or_(
                    Game.name.ilike(pattern),
                    Game.product_id.ilike(pattern),
                    Game.edition.ilike(pattern),
                    Game.description_short.ilike(pattern),
                )
            )
        prefix = f"{clean}%"
        with self.db.session() as session:
            stmt = (
                select(Game)
                .where(*token_filters)
                .order_by(
                    case((Game.name.ilike(prefix), 0), else_=1),
                    Game.popularity_rank.asc().nulls_last(),
                    Game.discount_percent.desc().nulls_last(),
                    func.lower(Game.name).asc(),
                )
                .limit(bounded)
            )
            rows = session.scalars(stmt).all()
            return [_hydrate_game(as_dict(row)) for row in rows]

    def suggest_names(self, q: str, limit: int = 8) -> list[dict]:
        """Return name suggestions for autocomplete from the local catalog."""
        clean = q.strip()
        if not clean:
            return []
        bounded = max(1, min(limit, 20))
        pattern = f"%{clean}%"
        prefix = f"{clean}%"
        with self.db.session() as session:
            stmt = (
                select(Game)
                .where(or_(Game.name.ilike(pattern), Game.product_id.ilike(pattern)))
                .order_by(
                    case((Game.name.ilike(prefix), 0), else_=1),
                    Game.discount_percent.desc().nulls_last(),
                    func.lower(Game.name).asc(),
                )
                .limit(bounded)
            )
            rows = session.scalars(stmt).all()
            return [_hydrate_game(as_dict(row)) for row in rows]

    # -------------------------------------------------------------------------
    # Single-game lookups, history, and scheduler helpers
    # -------------------------------------------------------------------------

    def mark_tracked(self, game_id: int) -> dict | None:
        """Mark a catalog game as actively tracked by the user."""
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(Game).where(Game.id == game_id).values(is_tracked=1, updated_at=now)
            )
            game = session.get(Game, game_id)
            return _hydrate_game(as_dict(game)) if game else None

    def set_catalog_meta(self, key: str, value: str) -> None:
        """Store a key/value pair describing catalog sync state (e.g. last sync time)."""
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                pg_insert(CatalogMeta)
                .values(key=key, value=value, updated_at=now)
                .on_conflict_do_update(
                    index_elements=[CatalogMeta.key],
                    set_={"value": value, "updated_at": now},
                )
            )

    def get_catalog_meta(self, key: str) -> str | None:
        """Read a single catalog_meta value, or None if the key does not exist."""
        with self.db.session() as session:
            return session.scalar(select(CatalogMeta.value).where(CatalogMeta.key == key))

    def catalog_count(self) -> int:
        """Return total number of rows in the games table."""
        with self.db.session() as session:
            return session.scalar(select(func.count()).select_from(Game)) or 0

    def admin_stats(self) -> dict:
        """Aggregate counts for the admin dashboard."""
        with self.db.session() as session:
            catalog_total = session.scalar(select(func.count()).select_from(Game)) or 0
            on_sale = (
                session.scalar(
                    select(func.count()).select_from(Game).where(Game.discount_percent > 0)
                )
                or 0
            )
            tracked = (
                session.scalar(
                    select(func.count()).select_from(Game).where(Game.is_tracked == 1)
                )
                or 0
            )
            library_entries = (
                session.scalar(select(func.count()).select_from(UserLibrary)) or 0
            )
            watches_total = session.scalar(select(func.count()).select_from(Watch)) or 0
            watches_enabled = (
                session.scalar(
                    select(func.count()).select_from(Watch).where(Watch.enabled == 1)
                )
                or 0
            )
            rows = session.execute(
                select(Notification.status, func.count().label("count")).group_by(
                    Notification.status
                )
            ).mappings().all()
            notification_counts = {row["status"]: row["count"] for row in rows}
        return {
            "catalog_total": catalog_total,
            "on_sale": on_sale,
            "tracked": tracked,
            "library_entries": library_entries,
            "watches_total": watches_total,
            "watches_enabled": watches_enabled,
            "notification_counts": notification_counts,
        }

    def list_watches_admin(
        self,
        *,
        q: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        filters = []
        if enabled_only:
            filters.append(Watch.enabled == 1)
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(
                    Game.name.ilike(pattern),
                    Watch.email.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )
        bounded = max(1, min(limit, 200))
        base = (
            select(Watch)
            .add_columns(
                Game.name.label("game_name"),
                Game.current_price_cents,
                Game.current_price_formatted,
                Game.store_url,
                User.email.label("user_email"),
            )
            .join(Game, Watch.game_id == Game.id)
            .outerjoin(User, Watch.user_id == User.id)
        )
        if filters:
            base = base.where(*filters)
        with self.db.session() as session:
            count_stmt = select(func.count()).select_from(Watch)
            if filters:
                count_stmt = (
                    count_stmt.join(Game, Watch.game_id == Game.id)
                    .outerjoin(User, Watch.user_id == User.id)
                    .where(*filters)
                )
            total = session.scalar(count_stmt) or 0
            stmt = base.order_by(Watch.created_at.desc()).limit(bounded).offset(max(0, offset))
            rows = session.execute(stmt).mappings().all()
            return [as_dict(row) for row in rows], total

    def list_notifications_admin(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        filters = []
        if status:
            filters.append(Notification.status == status)
        bounded = max(1, min(limit, 500))
        base = (
            select(Notification)
            .add_columns(
                Game.name.label("game_name"),
                User.email.label("user_email"),
            )
            .outerjoin(Game, Notification.game_id == Game.id)
            .outerjoin(User, Notification.user_id == User.id)
        )
        if filters:
            base = base.where(*filters)
        with self.db.session() as session:
            count_stmt = select(func.count()).select_from(Notification)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = session.scalar(count_stmt) or 0
            stmt = (
                base.order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(bounded)
                .offset(max(0, offset))
            )
            rows = session.execute(stmt).mappings().all()
            return [as_dict(row) for row in rows], total

    def list_games_admin(
        self,
        *,
        q: str | None = None,
        on_sale_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        return self.list_deals(
            q=q,
            on_sale_only=on_sale_only,
            sort="name",
            sort_dir="asc",
            limit=limit,
            offset=offset,
        )

    def list_library_admin(
        self,
        *,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        filters = []
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            filters.append(or_(Game.name.ilike(pattern), User.email.ilike(pattern)))
        bounded = max(1, min(limit, 200))
        base = (
            select(
                UserLibrary.user_id,
                UserLibrary.game_id,
                UserLibrary.created_at,
                Game.name.label("game_name"),
                Game.current_price_formatted,
                Game.discount_percent,
                User.email.label("user_email"),
            )
            .join(Game, UserLibrary.game_id == Game.id)
            .join(User, UserLibrary.user_id == User.id)
        )
        if filters:
            base = base.where(*filters)
        with self.db.session() as session:
            count_stmt = (
                select(func.count())
                .select_from(UserLibrary)
                .join(Game, UserLibrary.game_id == Game.id)
                .join(User, UserLibrary.user_id == User.id)
            )
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = session.scalar(count_stmt) or 0
            stmt = base.order_by(UserLibrary.created_at.desc()).limit(bounded).offset(max(0, offset))
            rows = session.execute(stmt).mappings().all()
            return [as_dict(row) for row in rows], total

    def admin_insights(self) -> dict:
        """Extended analytics for the admin command center."""
        with self.db.session() as session:
            recent_users = session.execute(
                select(
                    User.id,
                    User.email,
                    User.display_name,
                    User.email_verified_at,
                    User.created_at,
                )
                .order_by(User.created_at.desc())
                .limit(8)
            ).mappings().all()
            top_watched = session.execute(
                select(
                    Game.id,
                    Game.name,
                    Game.current_price_formatted,
                    func.count(Watch.id).label("watch_count"),
                )
                .join(Watch, Watch.game_id == Game.id)
                .where(Watch.enabled == 1)
                .group_by(Game.id)
                .order_by(func.count(Watch.id).desc(), func.lower(Game.name).asc())
                .limit(10)
            ).mappings().all()
            recent_watches = session.execute(
                select(
                    Watch.id,
                    Watch.created_at,
                    Game.name.label("game_name"),
                    User.email.label("user_email"),
                )
                .join(Game, Watch.game_id == Game.id)
                .outerjoin(User, Watch.user_id == User.id)
                .order_by(Watch.created_at.desc())
                .limit(8)
            ).mappings().all()
            recent_emails = session.execute(
                select(
                    Notification.id,
                    Notification.email,
                    Notification.subject,
                    Notification.status,
                    Notification.created_at,
                    Game.name.label("game_name"),
                )
                .outerjoin(Game, Notification.game_id == Game.id)
                .order_by(Notification.created_at.desc())
                .limit(8)
            ).mappings().all()
            price_history_rows = (
                session.scalar(select(func.count()).select_from(PriceHistory)) or 0
            )
            unverified_users = (
                session.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.email_verified_at.is_(None))
                )
                or 0
            )
            notification_emails = (
                session.scalar(select(func.count()).select_from(UserNotificationEmail)) or 0
            )
            avg_discount = session.scalar(
                select(func.avg(Game.discount_percent)).where(
                    Game.discount_percent.isnot(None),
                    Game.discount_percent > 0,
                )
            )
        return {
            "recent_users": [dict(row) for row in recent_users],
            "top_watched_games": [dict(row) for row in top_watched],
            "recent_watches": [dict(row) for row in recent_watches],
            "recent_emails": [dict(row) for row in recent_emails],
            "price_history_rows": price_history_rows,
            "unverified_users": unverified_users,
            "notification_emails": notification_emails,
            "avg_discount_percent": round(avg_discount or 0, 1),
        }

    def purge_notifications(
        self, *, status: str | None = None, older_than_days: int | None = None
    ) -> int:
        filters = []
        if status:
            filters.append(Notification.status == status)
        if older_than_days is not None and older_than_days > 0:
            cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
            filters.append(Notification.created_at < cutoff)
        with self.db.session() as session:
            stmt = delete(Notification)
            if filters:
                stmt = stmt.where(*filters)
            result = session.execute(stmt)
            return result.rowcount

    def get_game(self, game_id: int) -> dict | None:
        """Return a single game row by its integer id or None if missing."""
        with self.db.session() as session:
            game = session.get(Game, game_id)
            return _hydrate_game(as_dict(game)) if game else None

    def get_game_by_product(self, product_id: str, locale: str) -> dict | None:
        """Lookup a game by product_id and locale pair."""
        with self.db.session() as session:
            game = session.scalar(
                select(Game).where(Game.product_id == product_id, Game.locale == locale)
            )
            return _hydrate_game(as_dict(game)) if game else None

    def delete_game(self, game_id: int) -> bool:
        """Delete a game and cascade-delete related watches/history.

        Returns True when a row was deleted.
        """
        with self.db.session() as session:
            result = session.execute(delete(Game).where(Game.id == game_id))
            return result.rowcount > 0

    def get_history(self, game_id: int, limit: int = 50) -> list[dict]:
        """Return the most recent price history rows for a game."""
        with self.db.session() as session:
            rows = session.scalars(
                select(PriceHistory)
                .where(PriceHistory.game_id == game_id)
                .order_by(PriceHistory.checked_at.desc(), PriceHistory.id.desc())
                .limit(limit)
            ).all()
            return [as_dict(row) for row in rows]

    def due_games(self, check_interval_minutes: int) -> list[dict]:
        """Return library games due for a catalog price refresh.

        A game is "due" when ``last_checked_at`` is NULL or older than the
        configured interval.  The background scheduler uses this to decide when
        to call ``sync_deals``.
        """
        cutoff = (datetime.now(UTC) - timedelta(minutes=check_interval_minutes)).isoformat()
        with self.db.session() as session:
            rows = session.execute(
                select(
                    Game.id,
                    Game.product_id,
                    Game.locale,
                    Game.name,
                    Game.current_price_cents,
                )
                .join(UserLibrary, UserLibrary.game_id == Game.id)
                .where(or_(Game.last_checked_at.is_(None), Game.last_checked_at <= cutoff))
                .group_by(Game.id)
                .order_by(func.coalesce(func.min(Game.last_checked_at), func.min(Game.created_at)))
            ).mappings().all()
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
        with self.db.session() as session:
            watch = Watch(
                game_id=game_id,
                email=email,
                target_price_cents=target_price_cents,
                notify_on_any_drop=int(notify_on_any_drop),
                enabled=int(enabled),
                theme_id=theme_id,
                user_id=user_id,
                notification_email_id=notification_email_id,
                min_drop_cents=min_drop_cents,
                min_drop_percent=min_drop_percent,
                created_at=now,
                updated_at=now,
            )
            session.add(watch)
            session.flush()
            return as_dict(session.get(Watch, watch.id))

    def get_watch(self, watch_id: int, user_id: int | None = None) -> dict | None:
        """Return a single watch row by id or None if missing."""
        with self.db.session() as session:
            stmt = select(Watch).where(Watch.id == watch_id)
            if user_id is not None:
                stmt = stmt.where(Watch.user_id == user_id)
            return row_to_dict(session.scalar(stmt))

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
        with self.db.session() as session:
            session.execute(
                update(Watch)
                .where(Watch.id == watch_id)
                .values(
                    target_price_cents=new_target,
                    notify_on_any_drop=new_drop,
                    enabled=new_enabled,
                    min_drop_cents=new_min_cents,
                    min_drop_percent=new_min_pct,
                    notification_email_id=new_email_id,
                    email=new_email,
                    updated_at=now,
                )
            )
            return row_to_dict(session.get(Watch, watch_id))

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
        filters = []
        if game_id is not None:
            filters.append(Watch.game_id == game_id)
        if enabled_only:
            filters.append(Watch.enabled == 1)
        if user_id is not None:
            filters.append(Watch.user_id == user_id)
        stmt = (
            select(Watch)
            .add_columns(
                Game.name.label("game_name"),
                Game.current_price_cents,
                Game.current_price_formatted,
                Game.currency,
                Game.store_url,
            )
            .join(Game, Watch.game_id == Game.id)
        )
        if filters:
            stmt = stmt.where(*filters)
        stmt = stmt.order_by(Watch.created_at.desc())
        with self.db.session() as session:
            rows = session.execute(stmt).mappings().all()
            return [as_dict(row) for row in rows]

    def delete_watch(self, watch_id: int, user_id: int | None = None) -> bool:
        """Delete a watch by id. Returns True when a row was deleted."""
        with self.db.session() as session:
            stmt = delete(Watch).where(Watch.id == watch_id)
            if user_id is not None:
                stmt = stmt.where(Watch.user_id == user_id)
            result = session.execute(stmt)
            return result.rowcount > 0

    def mark_watch_notified(self, watch_id: int, price_cents: int | None) -> None:
        """Record the last notification price and timestamp for a watch.

        The service layer consults these fields to avoid sending duplicate
        emails when the price has not dropped further since the last alert.
        """
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(Watch)
                .where(Watch.id == watch_id)
                .values(
                    last_notified_price_cents=price_cents,
                    last_notified_at=now,
                    updated_at=now,
                )
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
        with self.db.session() as session:
            notification = Notification(
                watch_id=watch_id,
                game_id=game_id,
                email=email,
                subject=subject,
                body=body,
                status=status,
                reason=reason,
                error=error,
                created_at=now,
                sent_at=sent_at,
                user_id=user_id,
            )
            session.add(notification)
            session.flush()
            return as_dict(session.get(Notification, notification.id))

    def list_notifications(self, limit: int = 50, user_id: int | None = None) -> list[dict]:
        """Return recent notification log entries joined with game name."""
        with self.db.session() as session:
            stmt = (
                select(Notification)
                .add_columns(Game.name.label("game_name"))
                .outerjoin(Game, Notification.game_id == Game.id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
            )
            if user_id is not None:
                stmt = stmt.where(
                    Notification.user_id == user_id,
                    func.coalesce(Notification.reason, "") != "system",
                )
            rows = session.execute(stmt).mappings().all()
            return [as_dict(row) for row in rows]

    def delete_notification(self, notification_id: int, user_id: int | None = None) -> bool:
        """Delete one notification log row. Returns True when a row was deleted."""
        with self.db.session() as session:
            stmt = delete(Notification).where(Notification.id == notification_id)
            if user_id is not None:
                stmt = stmt.where(Notification.user_id == user_id)
            result = session.execute(stmt)
            return result.rowcount > 0

    def delete_notifications(self, notification_ids: list[int], user_id: int | None = None) -> int:
        """Delete many notification rows at once. Returns the number deleted."""
        if not notification_ids:
            return 0
        unique_ids = list(dict.fromkeys(notification_ids))
        with self.db.session() as session:
            stmt = delete(Notification).where(Notification.id.in_(unique_ids))
            if user_id is not None:
                stmt = stmt.where(Notification.user_id == user_id)
            result = session.execute(stmt)
            return result.rowcount


# -----------------------------------------------------------------------------
# Module-level helpers — row hydration and serialization
# -----------------------------------------------------------------------------


def _game_lite_select(*, exclude_is_tracked: bool = False):
    cols = [
        Game.id,
        Game.product_id,
        Game.locale,
        Game.name,
        Game.image_url,
        Game.store_url,
        Game.currency,
        Game.current_price_cents,
        Game.current_price_formatted,
        Game.original_price_cents,
        Game.original_price_formatted,
        Game.discount_text,
        Game.availability,
        Game.last_checked_at,
        Game.last_error,
        Game.discount_percent,
    ]
    if not exclude_is_tracked:
        cols.append(Game.is_tracked)
    cols.extend([Game.created_at, Game.updated_at])
    return select(*cols)


def _deals_filters(
    *,
    q: str | None,
    platform: str | None,
    min_discount: int | None,
    max_price_cents: int | None,
    on_sale_only: bool,
) -> list:
    filters = []
    if on_sale_only:
        filters.append(
            or_(
                and_(Game.discount_percent.isnot(None), Game.discount_percent > 0),
                and_(
                    Game.original_price_cents.isnot(None),
                    Game.current_price_cents.isnot(None),
                    Game.original_price_cents > Game.current_price_cents,
                ),
            )
        )
    if q:
        filters.append(Game.name.ilike(f"%{q.strip()}%"))
    if platform:
        filters.append(Game.platforms.ilike(f'%"{platform}"%'))
    if min_discount is not None and min_discount > 0:
        filters.append(Game.discount_percent >= min_discount)
    if max_price_cents is not None:
        filters.append(Game.current_price_cents <= max_price_cents)
    return filters


def _deals_order_by(sort: str, sort_dir: str) -> list:
    descending = sort_dir != "asc"
    name_asc = func.lower(Game.name).asc()

    def _col(column, *, nulls: bool = True):
        ordered = column.desc() if descending else column.asc()
        return ordered.nulls_last() if nulls else ordered

    order_map = {
        "popularity": [_col(Game.popularity_rank), name_asc],
        "discount": [_col(Game.discount_percent), name_asc],
        "savings": [_col(Game.original_price_cents - Game.current_price_cents)],
        "savings_percent": [_col(Game.discount_percent), name_asc],
        "price": [_col(Game.current_price_cents)],
        "original": [_col(Game.original_price_cents)],
        "name": [func.lower(Game.name).desc() if descending else name_asc],
        "newest": [
            Game.catalog_synced_at.desc() if descending else Game.catalog_synced_at.asc(),
            Game.updated_at.desc() if descending else Game.updated_at.asc(),
        ],
        "rating": [_col(Game.rating_average), _col(Game.rating_count)],
    }
    return order_map.get(sort, order_map["discount"])


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

    List fields (genres, screenshots, etc.) are stored as JSON text.
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
    """Serialize a Python list to a JSON string for storage, or None."""
    if not values:
        return None
    if isinstance(values, (list, tuple)):
        return json.dumps(list(values))
    return None
