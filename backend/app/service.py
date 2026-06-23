"""Business logic layer for price tracking and watch evaluation.

PriceService orchestrates the Store client, the Repository and the
EmailNotifier to implement high-level operations used by the API and
the scheduler: adding/refreshing products, searching the store,
creating/updating watches, and evaluating notifications when prices
change.
"""

from __future__ import annotations

import asyncio
import logging
import re

from backend.app.config import Settings
from backend.app.money import discount_percent
from backend.app.notifier import EmailNotifier
from backend.app.ps_store import PlayStationStoreClient, extract_product_ref, normalize_locale
from backend.app.repository import Repository, UNSET, utc_now_iso
from backend.app.service_helpers import normalize_product_lookup


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)


class PriceService:
    """Application-facing service providing price tracking operations."""

    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        store_client: PlayStationStoreClient,
        notifier: EmailNotifier,
    ):
        self.settings = settings
        self.repo = repo
        self.store_client = store_client
        self.notifier = notifier

    async def add_or_refresh_game(
        self, product_ref: str, locale: str | None = None, force: bool = False
    ) -> dict:
        """Add a catalog game to the library without calling the live store."""
        product_id, active_locale = normalize_product_lookup(product_ref, locale)
        game = self.repo.get_game_by_product(product_id, active_locale)
        if not game:
            raise ValueError(
                "game not in catalog — sync the PlayStation feed first, then add from search"
            )
        if not game.get("is_tracked"):
            game = self.repo.mark_tracked(game["id"]) or game
        return game

    async def track_catalog_game(self, game_id: int) -> dict:
        """Mark an existing catalog entry as tracked (database only)."""
        game = self.repo.get_game(game_id)
        if not game:
            raise KeyError("game not found")
        if game.get("is_tracked"):
            return game
        tracked = self.repo.mark_tracked(game_id)
        return tracked or game

    def bulk_track_games(self, game_ids: list[int]) -> list[dict]:
        """Mark multiple catalog games as library entries without store calls."""
        return self.repo.bulk_mark_tracked(game_ids)

    async def sync_deals(self, locale: str | None = None, force: bool = False) -> dict:
        """Pull the full PS Store catalog into the local database and evaluate watches."""
        active_locale = normalize_locale(locale or self.settings.store_locale)
        tracked_before = {
            g["id"]: g.get("current_price_cents")
            for g in self.repo.list_games(tracked_only=True)
        }
        catalog_rows = await self.store_client.fetch_deals(active_locale, force=force)
        count = self.repo.upsert_catalog_entries(catalog_rows)
        now = utc_now_iso()
        self.repo.set_catalog_meta("last_deals_sync", now)
        self.repo.set_catalog_meta("last_deals_count", str(count))
        self.repo.set_catalog_meta("last_deals_reported", str(len(catalog_rows)))
        self.repo.set_catalog_meta("last_catalog_sync", now)
        self.repo.set_catalog_meta("last_catalog_reported", str(len(catalog_rows)))

        for game in self.repo.list_games(tracked_only=True):
            previous = tracked_before.get(game["id"])
            current = game.get("current_price_cents")
            if previous is not None and current != previous:
                await self._evaluate_watches(game, previous)
            self.repo.mark_game_checked(game["id"], now)

        return {
            "synced": count,
            "fetched": len(catalog_rows),
            "locale": active_locale,
            "catalog_total": len(catalog_rows),
        }

    async def search_unified(
        self, query: str, locale: str | None, limit: int
    ) -> list[dict]:
        """Search the local catalog only (no live PlayStation Store calls)."""
        clean = " ".join(query.split())
        if not clean:
            return []
        bounded = max(1, min(limit, self.settings.max_search_limit))
        rows = await asyncio.to_thread(self.repo.search_catalog, clean, bounded)
        return [{**row, "source": "catalog"} for row in rows]

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
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "last_sync": self.repo.get_catalog_meta("last_deals_sync"),
        }

    def suggest(self, q: str, limit: int = 8) -> list[dict]:
        """Autocomplete suggestions from the local game catalog."""
        return self.repo.suggest_names(q, limit)

    async def refresh_game(self, game_id: int, force: bool = True) -> dict:
        """Refresh all catalog prices from PlayStation (same as sync-deals)."""
        await self.sync_deals(force=force)
        game = self.repo.get_game(game_id)
        if not game:
            raise KeyError("game not found")
        return game

    async def search(self, query: str, locale: str | None, limit: int) -> list[dict]:
        """Database-only search across the local catalog."""
        return await self.search_unified(query, locale, limit)

    async def refresh_due_games(self) -> dict:
        """Sync catalog prices when tracked library games are due for refresh."""
        due = self.repo.due_games(self.settings.check_interval_minutes)
        if not due:
            return {"due": 0, "refreshed": 0, "failed": [], "synced": False}
        try:
            result = await self.sync_deals(force=True)
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

    async def create_watch(
        self,
        game_id: int,
        email: str,
        target_price_cents: int | None,
        notify_on_any_drop: bool,
        enabled: bool,
        theme_id: str | None = None,
    ) -> dict:
        """Create a watch for a library game and optionally notify immediately."""
        self._validate_email(email)
        game = self.repo.get_game(game_id)
        if not game:
            raise KeyError("game not found")
        if not game.get("is_tracked"):
            raise ValueError("game must be in your library before deploying a watch")
        watch = self.repo.create_watch(
            game_id, email, target_price_cents, notify_on_any_drop, enabled, theme_id
        )
        if enabled and self._target_met(watch, game):
            await self.notifier.send_price_notification(
                watch, game, "target_met", theme_id=theme_id or watch.get("theme_id")
            )
        return self.repo.get_watch(watch["id"]) or watch

    async def bulk_create_watches(
        self,
        game_ids: list[int],
        email: str,
        target_price_cents: int | None,
        notify_on_any_drop: bool,
        enabled: bool,
        theme_id: str | None = None,
    ) -> dict:
        """Create watches for multiple library games."""
        self._validate_email(email)
        created: list[dict] = []
        skipped: list[dict] = []
        for game_id in dict.fromkeys(game_ids):
            game = self.repo.get_game(game_id)
            if not game:
                skipped.append({"game_id": game_id, "reason": "not found"})
                continue
            if not game.get("is_tracked"):
                self.repo.mark_tracked(game_id)
                game = self.repo.get_game(game_id) or game
            try:
                watch = await self.create_watch(
                    game_id,
                    email,
                    target_price_cents,
                    notify_on_any_drop,
                    enabled,
                    theme_id,
                )
                created.append(watch)
            except Exception as exc:
                skipped.append({"game_id": game_id, "reason": str(exc)})
        return {"created": created, "skipped": skipped}

    async def update_watch(
        self,
        watch_id: int,
        target_price_cents: int | None | object = UNSET,
        notify_on_any_drop: bool | None = None,
        enabled: bool | None = None,
    ) -> dict:
        watch = self.repo.update_watch(watch_id, target_price_cents, notify_on_any_drop, enabled)
        if not watch:
            raise KeyError("watch not found")
        return watch

    async def test_watch(self, watch_id: int) -> dict:
        watch = self.repo.get_watch(watch_id)
        if not watch:
            raise KeyError("watch not found")
        game = self.repo.get_game(watch["game_id"])
        if not game:
            raise KeyError("game not found")
        return await self.notifier.send_price_notification(
            watch, game, "test", test=True, theme_id=watch.get("theme_id")
        )

    async def _evaluate_watches(self, game: dict, previous_price_cents: int | None) -> None:
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
                and previous_price_cents is not None
                and current < previous_price_cents
            ):
                reason = "price_drop"
            if reason is None:
                continue
            last_notified = watch.get("last_notified_price_cents")
            if last_notified is not None and current >= last_notified:
                continue
            await self.notifier.send_price_notification(
                watch,
                game,
                reason,
                previous_price_cents=previous_price_cents,
                theme_id=watch.get("theme_id"),
            )

    def _target_met(self, watch: dict, game: dict) -> bool:
        target = watch.get("target_price_cents")
        current = game.get("current_price_cents")
        return target is not None and current is not None and current <= target

    def _validate_email(self, email: str) -> None:
        if not EMAIL_RE.match(email):
            raise ValueError("email is invalid")
