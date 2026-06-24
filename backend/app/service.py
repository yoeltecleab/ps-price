"""Business logic layer for price tracking and watch evaluation.

What is the "service layer"?
----------------------------
In a well-structured web app, code is split into layers:

1. **API / routes** — receive HTTP requests and return JSON responses.
2. **Service layer (this file)** — enforce *business rules*: "you must own the
   game before creating a watch", "only send email when the price actually
   dropped", etc.
3. **Repository layer** (``repository.py``) — run SQL to read/write the database.
4. **External clients** — talk to the PlayStation Store API, send email, etc.

``PriceService`` is the main class here.  It *orchestrates* those pieces: it
never writes raw SQL itself (that is the repository's job) and it never sends
HTTP to PlayStation directly (that is ``PlayStationStoreClient``'s job).

How watches and notifications work
----------------------------------
A **watch** is a user's instruction: "email me when this game's price hits $X"
or "email me on any price drop".  Watches live in the database (see
``repository.create_watch``).

When catalog prices are refreshed (``sync_deals``), the service compares each
library game's *new* price to its *old* price.  If a price changed, it calls
``_evaluate_watches`` for that game.  That method checks every enabled watch
and decides whether to fire a notification:

- **target_met** — current price is at or below the user's target.
- **price_drop** — user asked for "any drop" and the price went down.

Actual email delivery is delegated to ``EmailNotifier``; the repository only
*logs* what was sent (``log_notification``).
"""

from __future__ import annotations

import asyncio
import logging
import re

from datetime import UTC, datetime

from backend.app.auth_service import AuthService
from backend.app.config import Settings
from backend.app.notifier import EmailNotifier
from backend.app.ps_store import PlayStationStoreClient, extract_product_ref, normalize_locale
from backend.app.repository import Repository, UNSET, utc_now_iso
from backend.app.service_helpers import normalize_product_lookup


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)

# ``EMAIL_RE`` is a simple pattern check — full validation happens in AuthService.


class PriceService:
    """Application-facing service providing price tracking operations.

    Think of this class as the "brain" of the app.  API route handlers create
    one ``PriceService`` instance (with all its dependencies wired in) and call
    methods on it.  Each public method represents one user-facing action.
    """

    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        store_client: PlayStationStoreClient,
        notifier: EmailNotifier,
        auth_service: AuthService | None = None,
    ):
        # Dependencies are injected so we can swap real email/DB for fakes in tests.
        self.settings = settings
        self.repo = repo
        self.store_client = store_client
        self.notifier = notifier
        self.auth_service = auth_service

    # -------------------------------------------------------------------------
    # User library — adding and removing tracked games
    # -------------------------------------------------------------------------

    async def add_or_refresh_game(
        self, product_ref: str, locale: str | None = None, *, user_id: int
    ) -> dict:
        """Add a catalog game to the signed-in user's library.

        Business rule: we only add games that already exist in the local catalog
        (populated by ``sync_deals``).  We do *not* call the live PlayStation
        Store here — that keeps the endpoint fast and predictable.
        """
        product_id, active_locale = normalize_product_lookup(product_ref, locale)
        game = self.repo.get_game_by_product(product_id, active_locale)
        if not game:
            raise ValueError(
                "game not in catalog yet — wait for the catalog sync to finish, then search again"
            )
        self.repo.add_user_library(user_id, game["id"])
        game = self.repo.get_game(game["id"]) or game
        game["is_tracked"] = True
        return game

    def get_catalog_game_by_product(
        self, product_ref: str, locale: str | None = None
    ) -> dict:
        """Look up a catalog row by product id (database only)."""
        product_id, active_locale = normalize_product_lookup(product_ref, locale)
        game = self.repo.get_game_by_product(product_id, active_locale)
        if not game:
            raise KeyError("game not in catalog")
        return game

    async def track_catalog_game(self, game_id: int, *, user_id: int) -> dict:
        """Add an existing catalog entry to the signed-in user's library.

        Same outcome as ``add_or_refresh_game``, but the caller already knows
        the internal database ``game_id`` from search results.
        """
        game = self.repo.get_game(game_id)
        if not game:
            raise KeyError("game not found")
        self.repo.add_user_library(user_id, game_id)
        game = self.repo.get_game(game_id) or game
        game["is_tracked"] = True
        return game

    def bulk_track_games(self, game_ids: list[int], *, user_id: int) -> list[dict]:
        """Add multiple catalog games to the user's library in one request."""
        games = self.repo.bulk_add_user_library(user_id, game_ids)
        for game in games:
            game["is_tracked"] = True
        return games

    def remove_from_library(self, user_id: int, game_id: int) -> bool:
        """Remove a game from the user's library (and delete their watches for it)."""
        return self.repo.remove_user_library(user_id, game_id)

    # -------------------------------------------------------------------------
    # Catalog sync — fetch PlayStation prices and evaluate watches
    # -------------------------------------------------------------------------

    async def sync_catalog(self, locale: str | None = None, force: bool = False) -> dict:
        """Pull the full PS Store catalog into SQLite (all games, sale or not)."""
        active_locale = normalize_locale(locale or self.settings.store_locale)
        tracked_before = {
            g["id"]: g.get("current_price_cents")
            for g in self.repo.list_all_library_games()
        }
        catalog_rows = await self.store_client.fetch_deals(active_locale, force=force)
        count = self.repo.upsert_catalog_entries(catalog_rows)
        now = utc_now_iso()
        self.repo.set_catalog_meta("last_deals_sync", now)
        self.repo.set_catalog_meta("last_deals_count", str(count))
        self.repo.set_catalog_meta("last_deals_reported", str(len(catalog_rows)))
        self.repo.set_catalog_meta("last_catalog_sync", now)
        self.repo.set_catalog_meta("last_catalog_reported", str(len(catalog_rows)))
        self.repo.set_catalog_meta("last_catalog_refresh_at", now)

        for game in self.repo.list_all_library_games():
            full = self.repo.get_game(game["id"])
            if not full:
                continue
            previous = tracked_before.get(full["id"])
            current = full.get("current_price_cents")
            if previous is not None and current != previous:
                await self._evaluate_watches(full, previous)
            self.repo.mark_game_checked(full["id"], now)

        return {
            "synced": True,
            "upserted": count,
            "fetched": len(catalog_rows),
            "locale": active_locale,
            "catalog_total": self.repo.catalog_count(),
            "last_sync": now,
        }

    async def sync_deals(self, locale: str | None = None, force: bool = False) -> dict:
        """Backward-compatible alias for ``sync_catalog``."""
        result = await self.sync_catalog(locale, force=force)
        return {
            "synced": result.get("upserted", 0),
            "fetched": result.get("fetched", 0),
            "locale": result.get("locale"),
            "catalog_total": result.get("catalog_total", 0),
        }

    def catalog_refresh_status(self) -> dict:
        """Return global catalog refresh metadata for the UI cooldown."""
        last = (
            self.repo.get_catalog_meta("last_catalog_refresh_at")
            or self.repo.get_catalog_meta("last_catalog_sync")
        )
        cooldown = self.settings.catalog_refresh_cooldown_seconds
        elapsed = self._seconds_since_iso(last)
        retry_after = 0
        can_refresh = True
        if elapsed is not None and cooldown > 0 and elapsed < cooldown:
            can_refresh = False
            retry_after = int(cooldown - elapsed)
        return {
            "last_sync": last,
            "catalog_total": self.repo.catalog_count(),
            "synced_count": self.repo.get_catalog_meta("last_deals_count"),
            "fetched_count": self.repo.get_catalog_meta("last_deals_reported"),
            "cooldown_seconds": cooldown,
            "retry_after_seconds": retry_after,
            "can_refresh": can_refresh,
        }

    async def refresh_catalog_public(self, *, force: bool = False) -> dict:
        """Rate-limited full catalog refresh for UI buttons (shared across all users)."""
        status = self.catalog_refresh_status()
        if not force and not status["can_refresh"]:
            return {
                **status,
                "synced": False,
                "cooldown": True,
                "message": "Prices were refreshed recently. Showing cached catalog data.",
            }
        result = await self.sync_catalog(force=True)
        return {
            **self.catalog_refresh_status(),
            **result,
            "synced": True,
            "cooldown": False,
            "message": "Catalog refreshed from PlayStation Store.",
        }

    def _seconds_since_iso(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
        return (datetime.now(UTC) - parsed).total_seconds()

    # -------------------------------------------------------------------------
    # Search and browse — read-only catalog queries (no store HTTP)
    # -------------------------------------------------------------------------

    async def search_unified(
        self, query: str, locale: str | None, limit: int, user_id: int | None = None
    ) -> list[dict]:
        """Search the local catalog only (no live PlayStation Store calls)."""
        clean = " ".join(query.split())
        if not clean:
            return []
        bounded = max(1, min(limit, self.settings.max_search_limit))
        rows = await asyncio.to_thread(self.repo.search_catalog, clean, bounded)
        annotated = self.repo.annotate_user_tracked(user_id, rows)
        return [{**row, "source": "catalog"} for row in annotated]

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
        user_id: int | None = None,
    ) -> dict:
        """Return filtered catalog deals with total count for pagination."""
        items, total = self.repo.list_deals(
            q=q,
            platform=platform,
            min_discount=min_discount,
            max_price_cents=max_price_cents,
            on_sale_only=on_sale_only,
            sort=sort,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        return {
            "items": self.repo.annotate_user_tracked(user_id, items),
            "total": total,
            "limit": limit,
            "offset": offset,
            "last_sync": self.repo.get_catalog_meta("last_deals_sync"),
        }

    def suggest(self, q: str, limit: int = 8, user_id: int | None = None) -> list[dict]:
        """Autocomplete suggestions from the local game catalog."""
        rows = self.repo.suggest_names(q, limit)
        return self.repo.annotate_user_tracked(user_id, rows)

    async def refresh_game(self, game_id: int, force: bool = False) -> dict:
        """Refresh the full catalog (rate-limited); returns the requested game from DB."""
        game = self.repo.get_game(game_id)
        if not game:
            raise KeyError("game not found")
        await self.refresh_catalog_public(force=force)
        refreshed = self.repo.get_game(game_id)
        if not refreshed:
            raise KeyError("game not found")
        return refreshed

    def get_game_detail(self, game_id: int, user_id: int | None = None) -> dict:
        """Return a game with price history from the local database."""
        game = self.repo.get_game(game_id)
        if not game:
            raise KeyError("game not found")
        if user_id is not None:
            game["is_tracked"] = self.repo.user_has_library_game(user_id, game_id)
        game["history"] = self.repo.get_history(game_id)
        return game

    async def search(
        self, query: str, locale: str | None, limit: int, user_id: int | None = None
    ) -> list[dict]:
        """Database-only search across the local catalog."""
        return await self.search_unified(query, locale, limit, user_id=user_id)

    # -------------------------------------------------------------------------
    # Scheduled refresh — background job entry point
    # -------------------------------------------------------------------------

    async def refresh_due_games(self) -> dict:
        """Sync catalog prices when tracked library games are due for refresh.

        The scheduler calls this periodically.  Games are "due" when their
        ``last_checked_at`` is older than ``settings.check_interval_minutes``.
        """
        due = self.repo.due_games(self.settings.check_interval_minutes)
        if not due:
            return {"due": 0, "refreshed": 0, "failed": [], "synced": False}
        try:
            result = await self.sync_catalog(force=True)
            now = utc_now_iso()
            for game in due:
                self.repo.mark_game_checked(game["id"], now)
            return {
                "due": len(due),
                "refreshed": len(due),
                "failed": [],
                "synced": True,
                **result,
            }
        except Exception as exc:
            return {
                "due": len(due),
                "refreshed": 0,
                "failed": [{"error": str(exc)}],
                "synced": False,
            }

    # -------------------------------------------------------------------------
    # Watches — price alerts and email notifications
    # -------------------------------------------------------------------------

    async def create_watch(
        self,
        user_id: int,
        game_id: int,
        notification_email_id: int | None,
        target_price_cents: int | None,
        notify_on_any_drop: bool,
        enabled: bool,
        theme_id: str | None = None,
        min_drop_cents: int | None = None,
        min_drop_percent: int | None = None,
    ) -> dict:
        """Create a watch for a library game and optionally notify immediately.

        Business rules enforced here (not in the repository):

        - Game must already be in the user's library.
        - Email must be verified via ``AuthService``.
        - If the target price is *already* met, send one notification right away.
        """
        if not self.auth_service:
            raise RuntimeError("auth service not configured")
        game = self.repo.get_game(game_id)
        if not game:
            raise KeyError("game not found")
        if not self.repo.user_has_library_game(user_id, game_id):
            raise ValueError("game must be in your library before deploying a watch")
        email, resolved_email_id = self.auth_service.require_verified_notification_email(
            user_id, notification_email_id, None
        )
        watch = self.repo.create_watch(
            game_id,
            email,
            target_price_cents,
            notify_on_any_drop,
            enabled,
            theme_id,
            user_id=user_id,
            notification_email_id=resolved_email_id,
            min_drop_cents=min_drop_cents,
            min_drop_percent=min_drop_percent,
        )
        preferred = self._preferred_theme(user_id)
        if enabled and self._target_met(watch, game):
            await self.notifier.send_price_notification(
                watch,
                game,
                "target_met",
                user_preferred_theme=preferred,
            )
        return self.repo.get_watch(watch["id"]) or watch

    async def bulk_create_watches(
        self,
        user_id: int,
        game_ids: list[int],
        notification_email_id: int | None,
        target_price_cents: int | None,
        notify_on_any_drop: bool,
        enabled: bool,
        theme_id: str | None = None,
        min_drop_cents: int | None = None,
        min_drop_percent: int | None = None,
    ) -> dict:
        """Create watches for multiple library games.

        Games not in the library are auto-added before watch creation.  Failures
        for individual games are collected in ``skipped`` rather than aborting
        the whole batch.
        """
        created: list[dict] = []
        skipped: list[dict] = []
        for game_id in dict.fromkeys(game_ids):
            game = self.repo.get_game(game_id)
            if not game:
                skipped.append({"game_id": game_id, "reason": "not found"})
                continue
            if not self.repo.user_has_library_game(user_id, game_id):
                self.repo.add_user_library(user_id, game_id)
            try:
                watch = await self.create_watch(
                    user_id,
                    game_id,
                    notification_email_id,
                    target_price_cents,
                    notify_on_any_drop,
                    enabled,
                    theme_id,
                    min_drop_cents,
                    min_drop_percent,
                )
                created.append(watch)
            except Exception as exc:
                skipped.append({"game_id": game_id, "reason": str(exc)})
        return {"created": created, "skipped": skipped}

    async def update_watch(
        self,
        watch_id: int,
        user_id: int,
        target_price_cents: int | None | object = UNSET,
        notify_on_any_drop: bool | None = None,
        enabled: bool | None = None,
        min_drop_cents: int | None | object = UNSET,
        min_drop_percent: int | None | object = UNSET,
        notification_email_id: int | None | object = UNSET,
    ) -> dict:
        """Update watch settings including alert thresholds and notification email."""
        watch = self.repo.get_watch(watch_id, user_id)
        if not watch:
            raise KeyError("watch not found")
        email_kw: str | object = UNSET
        resolved_id_kw: int | None | object = UNSET
        if notification_email_id is not UNSET:
            email, resolved_id = self.auth_service.require_verified_notification_email(
                user_id,
                notification_email_id if notification_email_id is not None else watch.get("notification_email_id"),
                None,
            )
            email_kw = email
            resolved_id_kw = resolved_id
        updated = self.repo.update_watch(
            watch_id,
            target_price_cents,
            notify_on_any_drop,
            enabled,
            min_drop_cents,
            min_drop_percent,
            resolved_id_kw,
            email_kw,
        )
        if not updated:
            raise KeyError("watch not found")
        return updated

    async def test_watch(self, watch_id: int, user_id: int) -> dict:
        """Send a preview email so the user can see alert formatting."""
        watch = self.repo.get_watch(watch_id, user_id)
        if not watch:
            raise KeyError("watch not found")
        game = self.repo.get_game(watch["game_id"])
        if not game:
            raise KeyError("game not found")
        return await self.notifier.send_price_notification(
            watch,
            game,
            "preview",
            test=True,
            user_preferred_theme=self._preferred_theme(user_id),
        )

    # -------------------------------------------------------------------------
    # Private helpers — watch evaluation logic
    # -------------------------------------------------------------------------

    async def _evaluate_watches(self, game: dict, previous_price_cents: int | None) -> None:
        """Check every enabled watch on a game and send notifications when rules match.

        Called after a price sync when ``current_price != previous_price``.
        Each watch can trigger for one of two reasons:

        - ``target_met`` — price fell to the user's target (or below).
        - ``price_drop`` — user enabled "notify on any drop" and price went down.

        We skip sending if we already notified at this price or higher
        (``last_notified_price_cents``), which prevents duplicate emails when
        the catalog sync runs repeatedly.
        """
        current = game.get("current_price_cents")
        if current is None:
            return
        watches = self.repo.list_watches(game_id=game["id"], enabled_only=True)
        for watch in watches:
            reason = None
            if self._target_met(watch, game):
                reason = "target_met"
            if (
                reason is None
                and watch.get("notify_on_any_drop")
                and self._drop_qualifies(watch, previous_price_cents, current)
            ):
                reason = "min_drop" if watch.get("min_drop_cents") or watch.get("min_drop_percent") else "price_drop"
            if reason is None:
                continue
            last_notified = watch.get("last_notified_price_cents")
            if last_notified is not None and current >= last_notified:
                continue
            preferred = self._preferred_theme(watch.get("user_id"))
            await self.notifier.send_price_notification(
                watch,
                game,
                reason,
                previous_price_cents=previous_price_cents,
                user_preferred_theme=preferred,
            )

    def _preferred_theme(self, user_id: int | None) -> str | None:
        if not user_id or not self.auth_service:
            return None
        user = self.auth_service.auth_repo.get_user_by_id(user_id)
        return user.get("preferred_theme_id") if user else None

    def _drop_qualifies(self, watch: dict, previous: int | None, current: int) -> bool:
        if previous is None or current is None or current >= previous:
            return False
        drop_cents = previous - current
        drop_pct = int(round(drop_cents / previous * 100)) if previous else 0
        if watch.get("min_drop_cents") and drop_cents < watch["min_drop_cents"]:
            return False
        if watch.get("min_drop_percent") and drop_pct < watch["min_drop_percent"]:
            return False
        return True

    def _target_met(self, watch: dict, game: dict) -> bool:
        """Return True when the game's current price is at or below the watch target."""
        target = watch.get("target_price_cents")
        current = game.get("current_price_cents")
        return target is not None and current is not None and current <= target

    def _validate_email(self, email: str) -> None:
        """Raise ValueError if ``email`` does not look like a valid address."""
        if not EMAIL_RE.match(email):
            raise ValueError("email is invalid")
