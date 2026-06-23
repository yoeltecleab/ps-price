"""FastAPI application factory and HTTP endpoints for PS Price.

This module defines the FastAPI `app`, its startup/shutdown lifespan
that constructs core components (Database, Repository, PlayStation
Store client, Notifier, Service and Scheduler), and the HTTP routes
exposed to clients. Dependency helper functions (`service_dep`,
`repo_dep`, `settings_dep`) make these components available to route
handlers via FastAPI's dependency injection system.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import Settings, get_settings
from backend.app.database import Database
from backend.app.notifier import EmailNotifier
from backend.app.ps_store import PlayStationStoreClient
from backend.app.repository import Repository, UNSET
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
    """Typed container describing attributes attached to FastAPI app.state.

    This class is used only for developer clarity; FastAPI stores these
    attributes dynamically on `app.state` during startup.
    """
    settings: Settings
    db: Database
    repo: Repository
    store_client: PlayStationStoreClient
    notifier: EmailNotifier
    service: PriceService
    scheduler: PriceScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context: construct and wire components.

    The context manager runs at application startup and shutdown to
    initialize resources and ensure a graceful shutdown sequence
    (stop scheduler, close HTTP client).
    """
    settings = get_settings()
    db = Database(settings.database_path)
    db.migrate()
    repo = Repository(db)
    store_client = PlayStationStoreClient(settings)
    notifier = EmailNotifier(settings, repo)
    service = PriceService(settings, repo, store_client, notifier)
    scheduler = PriceScheduler(settings, service)

    app.state.settings = settings
    app.state.db = db
    app.state.repo = repo
    app.state.store_client = store_client
    app.state.notifier = notifier
    app.state.service = service
    app.state.scheduler = scheduler

    await scheduler.start()
    try:
        if settings.scheduler_enabled:

            async def _bootstrap_deals() -> None:
                try:
                    await service.sync_deals()
                except Exception:
                    logger.exception("Background deals sync failed")

            asyncio.create_task(_bootstrap_deals(), name="ps-price-deals-bootstrap")
        yield
    finally:
        await scheduler.stop()
        await store_client.close()


app = FastAPI(title="PS Price Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def service_dep() -> PriceService:
    return app.state.service


def repo_dep() -> Repository:
    return app.state.repo


def settings_dep() -> Settings:
    return app.state.settings


@app.get("/healthz")
def healthz(
    settings: Annotated[Settings, Depends(settings_dep)],
    scheduler: bool = Query(default=False, description="Include scheduler status"),
):
    payload = {
        "status": "ok",
        "app": settings.app_name,
        "database_path": settings.database_path,
        "email_configured": settings.smtp_configured,
    }
    if scheduler:
        payload["scheduler_running"] = app.state.scheduler.running
        payload["scheduler_enabled"] = settings.scheduler_enabled
    return payload


@app.get("/api/sync-status")
def sync_status(repo: Annotated[Repository, Depends(repo_dep)]):
    return {
        "last_sync": repo.get_catalog_meta("last_deals_sync"),
        "synced_count": repo.get_catalog_meta("last_deals_count"),
        "fetched_count": repo.get_catalog_meta("last_deals_reported"),
        "catalog_total": repo.catalog_count(),
    }


@app.get("/api/deals", response_model=DealsPageOut)
def list_deals(
    service: Annotated[PriceService, Depends(service_dep)],
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
    )


@app.get("/api/suggest", response_model=list[SuggestOut])
def suggest_games(
    service: Annotated[PriceService, Depends(service_dep)],
    q: str = Query(..., min_length=1),
    limit: int = Query(default=8, ge=1, le=20),
):
    return service.suggest(q, limit)


@app.post("/api/sync-deals")
async def sync_deals(
    service: Annotated[PriceService, Depends(service_dep)],
    locale: str | None = None,
    force: bool = Query(default=False),
):
    try:
        return await service.sync_deals(locale, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/games/{game_id}/track", response_model=GameOut)
async def track_catalog_game(
    game_id: int, service: Annotated[PriceService, Depends(service_dep)]
):
    try:
        return await service.track_catalog_game(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/search", response_model=list[SearchOut])
async def search_games(
    service: Annotated[PriceService, Depends(service_dep)],
    q: str = Query(..., min_length=1),
    locale: str | None = None,
    limit: int = Query(default=10, ge=1, le=48),
):
    try:
        return await service.search(q, locale, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/games/bulk-track", response_model=list[GameOut])
def bulk_track_games(
    payload: BulkTrackRequest, service: Annotated[PriceService, Depends(service_dep)]
):
    return service.bulk_track_games(payload.game_ids)


@app.post("/api/games", response_model=GameOut, status_code=status.HTTP_201_CREATED)
async def create_game(
    payload: GameCreate, service: Annotated[PriceService, Depends(service_dep)]
):
    try:
        return await service.add_or_refresh_game(payload.product_ref, payload.locale)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/games", response_model=list[GameOut])
def list_games(repo: Annotated[Repository, Depends(repo_dep)]):
    return repo.list_games()


@app.get("/api/games/{game_id}", response_model=GameDetail)
def get_game(game_id: int, repo: Annotated[Repository, Depends(repo_dep)]):
    game = repo.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    game["history"] = repo.get_history(game_id)
    return game


@app.post("/api/games/{game_id}/refresh", response_model=GameOut)
async def refresh_game(game_id: int, service: Annotated[PriceService, Depends(service_dep)]):
    try:
        return await service.refresh_game(game_id, force=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/api/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: int, repo: Annotated[Repository, Depends(repo_dep)]):
    if not repo.delete_game(game_id):
        raise HTTPException(status_code=404, detail="game not found")


@app.post("/api/watches", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
async def create_watch(
    payload: WatchCreate, service: Annotated[PriceService, Depends(service_dep)]
):
    try:
        return await service.create_watch(
            payload.game_id,
            payload.email,
            payload.target_price_cents,
            payload.notify_on_any_drop,
            payload.enabled,
            payload.theme_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/watches/bulk")
async def bulk_create_watches(
    payload: BulkWatchCreate, service: Annotated[PriceService, Depends(service_dep)]
):
    try:
        return await service.bulk_create_watches(
            payload.game_ids,
            payload.email,
            payload.target_price_cents,
            payload.notify_on_any_drop,
            payload.enabled,
            payload.theme_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/watches", response_model=list[WatchOut])
def list_watches(
    repo: Annotated[Repository, Depends(repo_dep)], game_id: int | None = None
):
    return repo.list_watches(game_id=game_id)


@app.patch("/api/watches/{watch_id}", response_model=WatchOut)
async def update_watch(
    watch_id: int,
    payload: WatchPatch,
    service: Annotated[PriceService, Depends(service_dep)],
):
    try:
        target_price = (
            payload.target_price_cents
            if "target_price_cents" in payload.model_fields_set
            else UNSET
        )
        return await service.update_watch(
            watch_id,
            target_price,
            payload.notify_on_any_drop,
            payload.enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/watches/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(watch_id: int, repo: Annotated[Repository, Depends(repo_dep)]):
    if not repo.delete_watch(watch_id):
        raise HTTPException(status_code=404, detail="watch not found")


@app.post("/api/watches/{watch_id}/test", response_model=NotificationOut)
async def test_watch(watch_id: int, service: Annotated[PriceService, Depends(service_dep)]):
    try:
        return await service.test_watch(watch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/notifications", response_model=list[NotificationOut])
def list_notifications(
    repo: Annotated[Repository, Depends(repo_dep)], limit: int = Query(default=50, ge=1, le=200)
):
    return repo.list_notifications(limit)


@app.delete("/api/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: int, repo: Annotated[Repository, Depends(repo_dep)]
):
    if not repo.delete_notification(notification_id):
        raise HTTPException(status_code=404, detail="notification not found")


@app.post("/api/notifications/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_notifications(
    payload: BulkDeleteNotifications, repo: Annotated[Repository, Depends(repo_dep)]
):
    deleted = repo.delete_notifications(payload.ids)
    return {"deleted": deleted}


@app.post("/api/refresh-due")
async def refresh_due(service: Annotated[PriceService, Depends(service_dep)]):
    return await service.refresh_due_games()
