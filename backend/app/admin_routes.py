"""Admin HTTP API — metrics, user management, and system controls."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.admin_service import AdminService
from backend.app.deps import AdminUserDep

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin_service(request: Request) -> AdminService:
    return AdminService(
        request.app.state.settings,
        request.app.state.repo,
        request.app.state.auth_repo,
        request.app.state.auth_service,
        request.app.state.service,
    )


AdminServiceDep = Annotated[AdminService, Depends(_admin_service)]


@router.get("/overview")
def admin_overview(_admin: AdminUserDep, service: AdminServiceDep):
    return service.overview()


@router.get("/insights")
def admin_insights(_admin: AdminUserDep, service: AdminServiceDep):
    return service.insights()


@router.get("/users")
def admin_list_users(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_users(q=q, limit=limit, offset=offset)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(user_id: int, admin: AdminUserDep, service: AdminServiceDep):
    try:
        service.delete_user(user_id, actor_id=admin["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return None


@router.post("/users/{user_id}/verify")
async def admin_verify_user(user_id: int, _admin: AdminUserDep, service: AdminServiceDep):
    try:
        await service.verify_user(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return {"verified": True}


@router.post("/users/{user_id}/resend-verification")
async def admin_resend_verification(
    user_id: int, _admin: AdminUserDep, service: AdminServiceDep
):
    try:
        await service.resend_verification(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"sent": True}


@router.post("/users/{user_id}/revoke-sessions")
def admin_revoke_sessions(user_id: int, _admin: AdminUserDep, service: AdminServiceDep):
    try:
        count = service.revoke_user_sessions(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return {"revoked": count}


@router.get("/watches")
def admin_list_watches(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    q: str | None = None,
    enabled_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_watches(
        q=q, enabled_only=enabled_only, limit=limit, offset=offset
    )


@router.delete("/watches/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_watch(watch_id: int, _admin: AdminUserDep, service: AdminServiceDep):
    try:
        service.delete_watch(watch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="watch not found") from exc
    return None


@router.get("/notifications")
def admin_list_notifications(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return service.list_notifications(status=status_filter, limit=limit, offset=offset)


@router.delete("/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_notification(
    notification_id: int, _admin: AdminUserDep, service: AdminServiceDep
):
    try:
        service.delete_notification(notification_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="notification not found") from exc
    return None


@router.post("/notifications/purge")
def admin_purge_notifications(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    status_filter: str | None = Query(default=None, alias="status"),
    older_than_days: int | None = Query(default=None, ge=1, le=3650),
):
    deleted = service.purge_notifications(
        status=status_filter, older_than_days=older_than_days
    )
    return {"deleted": deleted}


@router.get("/games")
def admin_list_games(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    q: str | None = None,
    on_sale_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_games(
        q=q, on_sale_only=on_sale_only, limit=limit, offset=offset
    )


@router.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_game(game_id: int, _admin: AdminUserDep, service: AdminServiceDep):
    try:
        service.delete_game(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="game not found") from exc
    return None


@router.post("/games/{game_id}/refresh")
async def admin_refresh_game(game_id: int, _admin: AdminUserDep, service: AdminServiceDep):
    try:
        game = await service.refresh_game(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="game not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"game": game}


@router.get("/library")
def admin_list_library(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_library(q=q, limit=limit, offset=offset)


@router.get("/sessions")
def admin_list_sessions(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_sessions(q=q, limit=limit, offset=offset)


@router.get("/passkeys")
def admin_list_passkeys(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_passkeys(q=q, limit=limit, offset=offset)


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_passkey(passkey_id: int, _admin: AdminUserDep, service: AdminServiceDep):
    try:
        service.delete_passkey(passkey_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="passkey not found") from exc
    return None


@router.get("/notification-emails")
def admin_list_notification_emails(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    q: str | None = None,
    verified_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_notification_emails(
        q=q, verified_only=verified_only, limit=limit, offset=offset
    )


@router.post("/sync")
async def admin_force_sync(
    _admin: AdminUserDep,
    service: AdminServiceDep,
    locale: str | None = None,
    background: bool = Query(default=True),
):
    try:
        return await service.force_sync(locale=locale, background=background)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/refresh-due")
async def admin_refresh_due(_admin: AdminUserDep, service: AdminServiceDep):
    return await service.refresh_due()
