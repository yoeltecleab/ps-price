"""FastAPI application — HTTP entry point for the PS Price backend.

This is the **front door** of the server. Every browser/API request from the
Next.js frontend hits a function in this file (a "route handler").

Architecture (request flow)::

    Browser  →  FastAPI route (this file)  →  PriceService / AuthService
                     ↓                              ↓
              deps.py (who is logged in?)     repository.py (SQL)
                                                     ↓
                                               SQLite database

Startup (``lifespan``):
  1. Load settings and validate production security rules
  2. Open SQLite and run migrations (create tables if needed)
  3. Build service objects and store them on ``app.state``
  4. Start background ``PriceScheduler`` (periodic sync + price checks)
  5. On shutdown: stop scheduler and close HTTP client

Routes are grouped by feature:
  - ``/healthz``, ``/api/sync-status`` — ops/monitoring
  - ``/api/deals``, ``/api/search`` — public catalog browsing
  - ``/api/games``, ``/api/watches`` — per-user library (login required)
  - ``/api/auth/*`` — in ``auth_routes.py`` (included via ``include_router``)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.auth_repository import AuthRepository
from backend.app.auth_routes import router as auth_router
from backend.app.auth_service import AuthService
from backend.app.config import Settings, get_settings
from backend.app.database import Database
from backend.app.deps import AdminUserDep, OptionalUserDep, VerifiedUserDep
from backend.app.notifier import EmailNotifier
from backend.app.ps_store import PlayStationStoreClient
from backend.app.repository import Repository, UNSET
from backend.app.rate_limit import rate_limiter
from backend.app.scheduler import PriceScheduler
from backend.app.schemas import (
    BulkDeleteNotifications,
    BulkTrackRequest,
    BulkWatchCreate,
    DealsPageOut,
    GameCreate,
    GameDetail,
    GameOut,
    NotificationOut,
    SearchOut,
    SuggestOut,
    WatchCreate,
    WatchOut,
    WatchPatch,
)
from backend.app.service import PriceService


logger = logging.getLogger(__name__)


class AppState:
    """Type hint for objects hung on ``app.state`` after startup.

    FastAPI's ``app.state`` is a bag of attributes shared across requests.
    Dependencies in ``deps.py`` read from here instead of creating new DB
    connections on every request.
    """

    settings: Settings
    db: Database
    repo: Repository
    auth_repo: AuthRepository
    store_client: PlayStationStoreClient
    notifier: EmailNotifier
    auth_service: AuthService
    service: PriceService
    scheduler: PriceScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run once when the server starts and once when it shuts down.

    ``yield`` separates startup from shutdown. Code before ``yield`` runs when
    Uvicorn loads the app; code after runs on graceful shutdown.
    """
    settings = get_settings()
    settings.validate_production_settings()

    # --- Wire up persistence and services (order matters: DB first) ---
    db = Database(settings.database_path)
    db.migrate()
    repo = Repository(db)
    auth_repo = AuthRepository(db)
    store_client = PlayStationStoreClient(settings)
    notifier = EmailNotifier(settings, repo)
    auth_service = AuthService(settings, auth_repo, repo, notifier)
    service = PriceService(settings, repo, store_client, notifier, auth_service)
    scheduler = PriceScheduler(settings, service)

    app.state.settings = settings
    app.state.db = db
    app.state.repo = repo
    app.state.auth_repo = auth_repo
    app.state.store_client = store_client
    app.state.notifier = notifier
    app.state.auth_service = auth_service
    app.state.service = service
    app.state.scheduler = scheduler

    await scheduler.start()

    async def _startup_catalog_sync() -> None:
        if not settings.sync_on_startup:
            return
        logger.info("Startup catalog sync queued")
        await service.start_catalog_sync(force=True)

    startup_sync_task = asyncio.create_task(
        _startup_catalog_sync(), name="ps-price-startup-sync"
    )

    try:
        yield
    finally:
        startup_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await startup_sync_task
        await scheduler.stop()
        await store_client.close()


app = FastAPI(title="PS Price Backend", version="0.2.0", lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard browser security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if get_settings().production_mode:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)
# CORS lets the Next.js frontend (different port) call this API with cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Mount all /api/auth/* routes from auth_routes.py
app.include_router(auth_router)


# ---------------------------------------------------------------------------
# Dependency helpers — return shared singletons from app.state
# ---------------------------------------------------------------------------

def service_dep() -> PriceService:
    return app.state.service


def repo_dep() -> Repository:
    return app.state.repo


def settings_dep() -> Settings:
    return app.state.settings


# ---------------------------------------------------------------------------
# Health & sync status (mostly public)
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz(
    settings: Annotated[Settings, Depends(settings_dep)],
    scheduler: bool = Query(default=False, description="Include scheduler status"),
):
    payload: dict[str, object] = {"status": "ok"}
    if scheduler:
        payload["scheduler_running"] = app.state.scheduler.running
        payload["scheduler_enabled"] = settings.scheduler_enabled
    return payload


@app.get("/api/sync-status")
def sync_status(service: Annotated[PriceService, Depends(service_dep)]):
    """Return catalog sync metadata and UI refresh cooldown state."""
    return service.catalog_refresh_status()


@app.post("/api/catalog/refresh")
async def refresh_catalog_public(
    service: Annotated[PriceService, Depends(service_dep)],
):
    """Rate-limited full catalog refresh (shared cooldown across all users)."""
    try:
        return await service.refresh_catalog_public()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Catalog browsing (login optional — shows "tracked" if you are signed in)
# ---------------------------------------------------------------------------

@app.get("/api/deals", response_model=DealsPageOut)
def list_deals(
    service: Annotated[PriceService, Depends(service_dep)],
    user: OptionalUserDep,
    q: str | None = None,
    platform: str | None = None,
    min_discount: int | None = Query(default=None, ge=0, le=100),
    max_price_cents: int | None = Query(default=None, ge=0),
    on_sale_only: bool = True,
    sort: str = Query(
        default="discount",
        pattern=(
            "^(popularity|discount|savings|savings_percent|price|"
            "original|name|newest|rating)$"
        ),
    ),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=48, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    user_id = user["id"] if user else None
    return service.list_deals(
        q=q,
        platform=platform,
        min_discount=min_discount,
        max_price_cents=max_price_cents,
        on_sale_only=on_sale_only,
        sort=sort,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
        user_id=user_id,
    )


@app.get("/api/suggest", response_model=list[SuggestOut])
def suggest_games(
    service: Annotated[PriceService, Depends(service_dep)],
    user: OptionalUserDep,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=8, ge=1, le=20),
):
    user_id = user["id"] if user else None
    return service.suggest(q, limit, user_id=user_id)


# ---------------------------------------------------------------------------
# Admin-only catalog sync (see PS_PRICE_ADMIN_EMAILS)
# ---------------------------------------------------------------------------

@app.post("/api/sync-deals")
async def sync_deals(
    service: Annotated[PriceService, Depends(service_dep)],
    user: AdminUserDep,
    locale: str | None = None,
    force: bool = Query(default=True),
):
    try:
        return await service.sync_catalog(locale, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# User library — tracked games (verified login required)
# ---------------------------------------------------------------------------

@app.post("/api/games/{game_id}/track", response_model=GameOut)
async def track_catalog_game(
    game_id: int,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    try:
        return await service.track_catalog_game(game_id, user_id=user["id"])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/search", response_model=list[SearchOut])
async def search_games(
    service: Annotated[PriceService, Depends(service_dep)],
    user: OptionalUserDep,
    q: str = Query(..., min_length=1),
    locale: str | None = None,
    limit: int = Query(default=10, ge=1, le=48),
):
    user_id = user["id"] if user else None
    try:
        return await service.search(q, locale, limit, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/games/bulk-track", response_model=list[GameOut])
def bulk_track_games(
    payload: BulkTrackRequest,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    return service.bulk_track_games(payload.game_ids, user_id=user["id"])


@app.post("/api/games", response_model=GameOut, status_code=status.HTTP_201_CREATED)
async def create_game(
    payload: GameCreate,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    try:
        return await service.add_or_refresh_game(
            payload.product_ref, payload.locale, user_id=user["id"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/games", response_model=list[GameOut])
def list_games(
    repo: Annotated[Repository, Depends(repo_dep)],
    user: VerifiedUserDep,
):
    return repo.list_games_for_user(user["id"])


@app.get("/api/games/{game_id}", response_model=GameDetail)
async def get_game(
    game_id: int,
    service: Annotated[PriceService, Depends(service_dep)],
    user: OptionalUserDep,
):
    try:
        user_id = user["id"] if user else None
        return await service.get_game_detail(game_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="game not found") from exc


@app.post("/api/games/{game_id}/refresh", response_model=GameOut)
async def refresh_game(
    game_id: int,
    service: Annotated[PriceService, Depends(service_dep)],
):
    try:
        return await service.refresh_game(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/api/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_library_game(
    game_id: int,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    if not service.remove_from_library(user["id"], game_id):
        raise HTTPException(status_code=404, detail="game not in library")


# ---------------------------------------------------------------------------
# Price watches & email alerts
# ---------------------------------------------------------------------------

@app.post("/api/watches", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
async def create_watch(
    payload: WatchCreate,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    try:
        return await service.create_watch(
            user["id"],
            payload.game_id,
            payload.notification_email_id,
            payload.target_price_cents,
            payload.notify_on_any_drop,
            payload.enabled,
            payload.theme_id,
            payload.min_drop_cents,
            payload.min_drop_percent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/watches/bulk")
async def bulk_create_watches(
    payload: BulkWatchCreate,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    try:
        return await service.bulk_create_watches(
            user["id"],
            payload.game_ids,
            payload.notification_email_id,
            payload.target_price_cents,
            payload.notify_on_any_drop,
            payload.enabled,
            payload.theme_id,
            payload.min_drop_cents,
            payload.min_drop_percent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/watches", response_model=list[WatchOut])
def list_watches(
    repo: Annotated[Repository, Depends(repo_dep)],
    user: VerifiedUserDep,
    game_id: int | None = None,
):
    return repo.list_watches(game_id=game_id, user_id=user["id"])


@app.patch("/api/watches/{watch_id}", response_model=WatchOut)
async def update_watch(
    watch_id: int,
    payload: WatchPatch,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    try:
        target_price = (
            payload.target_price_cents
            if "target_price_cents" in payload.model_fields_set
            else UNSET
        )
        min_drop_cents = (
            payload.min_drop_cents if "min_drop_cents" in payload.model_fields_set else UNSET
        )
        min_drop_percent = (
            payload.min_drop_percent if "min_drop_percent" in payload.model_fields_set else UNSET
        )
        notification_email_id = (
            payload.notification_email_id
            if "notification_email_id" in payload.model_fields_set
            else UNSET
        )
        return await service.update_watch(
            watch_id,
            user["id"],
            target_price,
            payload.notify_on_any_drop,
            payload.enabled,
            min_drop_cents,
            min_drop_percent,
            notification_email_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/watches/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(
    watch_id: int,
    repo: Annotated[Repository, Depends(repo_dep)],
    user: VerifiedUserDep,
):
    if not repo.delete_watch(watch_id, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="watch not found")


@app.post("/api/watches/{watch_id}/test", response_model=NotificationOut)
async def test_watch(
    watch_id: int,
    request: Request,
    service: Annotated[PriceService, Depends(service_dep)],
    user: VerifiedUserDep,
):
    rate_limiter.check(f"watch-test:{user['id']}", limit=5, window_seconds=3600)
    try:
        return await service.test_watch(watch_id, user["id"])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Notification log (emails sent or skipped)
# ---------------------------------------------------------------------------

@app.get("/api/notifications", response_model=list[NotificationOut])
def list_notifications(
    repo: Annotated[Repository, Depends(repo_dep)],
    user: VerifiedUserDep,
    limit: int = Query(default=50, ge=1, le=200),
):
    return repo.list_notifications(limit, user_id=user["id"])


@app.delete("/api/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: int,
    repo: Annotated[Repository, Depends(repo_dep)],
    user: VerifiedUserDep,
):
    if not repo.delete_notification(notification_id, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="notification not found")


@app.post("/api/notifications/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_notifications(
    payload: BulkDeleteNotifications,
    repo: Annotated[Repository, Depends(repo_dep)],
    user: VerifiedUserDep,
):
    deleted = repo.delete_notifications(payload.ids, user_id=user["id"])
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Admin: refresh all games that are due for a price check
# ---------------------------------------------------------------------------

@app.post("/api/refresh-due")
async def refresh_due(
    service: Annotated[PriceService, Depends(service_dep)],
    user: AdminUserDep,
):
    return await service.refresh_due_games()
