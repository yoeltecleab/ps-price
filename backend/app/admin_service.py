"""Admin-only operations: metrics, user management, and system controls."""

from __future__ import annotations

from pathlib import Path

from backend.app.auth_repository import AuthRepository
from backend.app.auth_service import AuthService
from backend.app.config import Settings
from backend.app.rate_limit import rate_limiter
from backend.app.repository import Repository
from backend.app.service import PriceService


class AdminService:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        auth_repo: AuthRepository,
        auth_service: AuthService,
        price_service: PriceService,
    ):
        self.settings = settings
        self.repo = repo
        self.auth_repo = auth_repo
        self.auth_service = auth_service
        self.price_service = price_service

    def overview(self) -> dict:
        stats = self.repo.admin_stats()
        user_stats = self.auth_repo.admin_user_stats()
        insights = self.repo.admin_insights()
        sync = self.price_service.catalog_refresh_status()
        db_info = self._database_info()
        return {
            "users": user_stats,
            "catalog": {
                "total_games": stats["catalog_total"],
                "on_sale": stats["on_sale"],
                "tracked": stats["tracked"],
                "library_entries": stats["library_entries"],
            },
            "watches": {
                "total": stats["watches_total"],
                "enabled": stats["watches_enabled"],
            },
            "notifications": stats["notification_counts"],
            "sync": sync,
            "insights": insights,
            "system": {
                "scheduler_enabled": self.settings.scheduler_enabled,
                "sync_on_startup": self.settings.sync_on_startup,
                "smtp_configured": self.settings.smtp_configured,
                "store_locale": self.settings.store_locale,
                "production_mode": self.settings.production_mode,
                "database_backend": db_info["backend"],
                "database_bytes": db_info["bytes"],
                "database_path": db_info["path"],
                "database_url_set": db_info["url_set"],
                "rate_limit_buckets": rate_limiter.active_bucket_count(),
                "check_interval_minutes": self.settings.check_interval_minutes,
                "feed_sync_interval_minutes": self.settings.feed_sync_interval_minutes,
            },
        }

    def _database_info(self) -> dict:
        if self.settings.database_url:
            with self.repo.db.connect() as conn:
                row = conn.execute(
                    "SELECT pg_database_size(current_database()) AS size"
                ).fetchone()
            size = row[0]
            return {
                "backend": "postgresql",
                "bytes": int(size),
                "path": "",
                "url_set": True,
            }
        db_path = Path(self.settings.database_path)
        return {
            "backend": "sqlite",
            "bytes": db_path.stat().st_size if db_path.exists() else 0,
            "path": str(db_path),
            "url_set": False,
        }

    def insights(self) -> dict:
        return self.repo.admin_insights()

    def list_users(self, *, q: str | None = None, limit: int = 50, offset: int = 0) -> dict:
        items, total = self.auth_repo.list_users_admin(q=q, limit=limit, offset=offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def delete_user(self, user_id: int, *, actor_id: int) -> None:
        if user_id == actor_id:
            raise ValueError("cannot delete your own account from the admin console")
        if not self.auth_repo.delete_user(user_id):
            raise KeyError("user not found")

    async def verify_user(self, user_id: int) -> None:
        user = self.auth_repo.get_user_by_id(user_id)
        if not user:
            raise KeyError("user not found")
        self.auth_repo.mark_email_verified(user_id)

    async def resend_verification(self, user_id: int) -> None:
        user = self.auth_repo.get_user_by_id(user_id)
        if not user:
            raise KeyError("user not found")
        if user.get("email_verified_at"):
            raise ValueError("user is already verified")
        await self.auth_service.resend_verification(user_id)

    def revoke_user_sessions(self, user_id: int) -> int:
        if not self.auth_repo.get_user_by_id(user_id):
            raise KeyError("user not found")
        return self.auth_repo.admin_revoke_user_sessions(user_id)

    def list_watches(
        self,
        *,
        q: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        items, total = self.repo.list_watches_admin(
            q=q, enabled_only=enabled_only, limit=limit, offset=offset
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def delete_watch(self, watch_id: int) -> None:
        if not self.repo.delete_watch(watch_id):
            raise KeyError("watch not found")

    def list_notifications(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        items, total = self.repo.list_notifications_admin(
            status=status, limit=limit, offset=offset
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def delete_notification(self, notification_id: int) -> None:
        if not self.repo.delete_notification(notification_id):
            raise KeyError("notification not found")

    def purge_notifications(
        self, *, status: str | None = None, older_than_days: int | None = None
    ) -> int:
        return self.repo.purge_notifications(status=status, older_than_days=older_than_days)

    def list_games(
        self,
        *,
        q: str | None = None,
        on_sale_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        items, total = self.repo.list_games_admin(
            q=q, on_sale_only=on_sale_only, limit=limit, offset=offset
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def delete_game(self, game_id: int) -> None:
        if not self.repo.delete_game(game_id):
            raise KeyError("game not found")

    async def refresh_game(self, game_id: int) -> dict:
        try:
            return await self.price_service.refresh_game(game_id, force=True)
        except KeyError:
            raise
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    def list_library(
        self, *, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> dict:
        items, total = self.repo.list_library_admin(q=q, limit=limit, offset=offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def list_sessions(
        self, *, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> dict:
        items, total = self.auth_repo.list_sessions_admin(q=q, limit=limit, offset=offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def list_passkeys(
        self, *, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> dict:
        items, total = self.auth_repo.list_passkeys_admin(q=q, limit=limit, offset=offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def delete_passkey(self, passkey_id: int) -> None:
        if not self.auth_repo.admin_delete_passkey(passkey_id):
            raise KeyError("passkey not found")

    def list_notification_emails(
        self,
        *,
        q: str | None = None,
        verified_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        items, total = self.auth_repo.list_notification_emails_admin(
            q=q, verified_only=verified_only, limit=limit, offset=offset
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def force_sync(self, *, locale: str | None = None, background: bool = True) -> dict:
        if background:
            return await self.price_service.start_catalog_sync(force=True)
        return await self.price_service.sync_catalog(locale=locale, force=True)

    async def refresh_due(self) -> dict:
        return await self.price_service.refresh_due_games()
