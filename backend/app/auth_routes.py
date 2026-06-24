"""HTTP API for sign-up, login, account settings, and passkeys.

**Where this file fits in the app**

Reading order for learning how auth works end-to-end:

1. **This file** — URLs, JSON bodies, cookies, status codes (what the frontend calls).
2. ``auth_service.py`` — validation, emails, WebAuthn verification.
3. ``auth_repository.py`` — SQLite queries.

Each route handler should stay small: rate-limit if needed → call ``AuthService`` →
map ``AuthError`` to ``HTTPException`` → set or clear the session cookie when
login/logout/register succeeds.

**Cookie security**

Session tokens are stored in an HTTP-only cookie (``ps_price_session``) so
JavaScript cannot read them (reduces XSS token theft). ``secure`` and ``samesite``
come from settings for HTTPS and CSRF-friendly defaults.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from backend.app.rate_limit import rate_limiter
from backend.app.security import user_is_admin
from backend.app.auth_service import AuthError, AuthService
from backend.app.config import Settings
from backend.app.deps import (
    AuthServiceDep,
    CurrentUserDep,
    RefreshTokenDep,
    SettingsDep,
    VerifiedUserDep,
)


# All routes in this file live under /api/auth (see main.py router include).
router = APIRouter(prefix="/api/auth", tags=["auth"])


# -----------------------------------------------------------------------------
# Request body models (Pydantic)
# -----------------------------------------------------------------------------
# These classes define the JSON shape the client must send. FastAPI validates
# automatically before your handler runs (wrong types → 422 Unprocessable Entity).


class RegisterBody(BaseModel):
    """POST /register — new account (password optional when using passkey signup)."""

    email: str
    password: str | None = Field(default=None, min_length=10)
    display_name: str | None = None


class RegisterPasskeyStartBody(BaseModel):
    """POST /register/passkey/options — passwordless signup step 1."""

    email: str
    display_name: str | None = None


class SetPasswordBody(BaseModel):
    """POST /set-password — initial password for passkey-only accounts."""

    new_password: str = Field(min_length=10)


class LoginBody(BaseModel):
    """POST /login — email + password."""

    email: str
    password: str


class VerifyEmailBody(BaseModel):
    """POST /verify-email — token from verification email."""

    token: str


class ForgotPasswordBody(BaseModel):
    """POST /forgot-password — request reset link (always returns success)."""

    email: str


class ResetPasswordBody(BaseModel):
    """POST /reset-password — new password + token from email."""

    token: str
    password: str = Field(min_length=10)


class ChangePasswordBody(BaseModel):
    """POST /change-password — logged-in user changes password."""

    current_password: str
    new_password: str = Field(min_length=10)


class ProfilePatchBody(BaseModel):
    """PATCH /profile — display name and/or preferred UI theme."""

    display_name: str | None = None
    preferred_theme_id: str | None = None


class PasskeyVerifyBody(BaseModel):
    """POST /passkey/register/verify — browser credential + optional label."""

    credential: dict[str, Any]
    friendly_name: str | None = None


class PasskeyLoginBody(BaseModel):
    """POST /passkey/login/verify — browser assertion after options step."""

    credential: dict[str, Any]


class PasskeyLoginOptionsBody(BaseModel):
    """POST /passkey/login/options — optional email to narrow allowed passkeys."""

    email: str | None = None


class NotificationEmailCreate(BaseModel):
    """POST /notification-emails — add alert address."""

    email: str
    label: str | None = None


class NotificationEmailVerify(BaseModel):
    """Body for notification email verify endpoints — token from email link."""

    token: str


# -----------------------------------------------------------------------------
# JWT cookie helpers
# -----------------------------------------------------------------------------


def _set_auth_cookies(
    response: Response, settings: Settings, access: str, refresh: str
) -> None:
    """Attach access and refresh JWTs as HttpOnly cookies."""
    response.set_cookie(
        key=AuthService.ACCESS_COOKIE,
        value=access,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_access_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=AuthService.REFRESH_COOKIE,
        value=refresh,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_refresh_ttl_days * 86400,
        path="/",
    )


def _set_access_cookie(response: Response, settings: Settings, access: str) -> None:
    """Update only the short-lived access JWT (after /refresh)."""
    response.set_cookie(
        key=AuthService.ACCESS_COOKIE,
        value=access,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_access_ttl_minutes * 60,
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    """Remove JWT cookies on logout."""
    for key in (AuthService.ACCESS_COOKIE, AuthService.REFRESH_COOKIE):
        response.delete_cookie(
            key,
            path="/",
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )


# -----------------------------------------------------------------------------
# Registration, login, logout, current user
# -----------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterBody,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
):
    """Create account, set session cookie, return public user JSON.

    Rate limited per IP to slow down mass sign-up abuse.
    """
    rate_limiter.check(
        f"register:{rate_limiter.client_ip(request)}",
        limit=5,
        window_seconds=3600,
    )
    try:
        user, access, refresh = await auth.register(
            body.email,
            body.password,
            display_name=body.display_name,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_auth_cookies(response, settings, access, refresh)
    return {"user": user}


@router.post("/register/passkey/options")
async def register_passkey_options(
    body: RegisterPasskeyStartBody,
    request: Request,
    auth: AuthServiceDep,
):
    """Create a passwordless account and return WebAuthn registration options."""
    rate_limiter.check(
        f"register:{rate_limiter.client_ip(request)}",
        limit=5,
        window_seconds=3600,
    )
    try:
        return await auth.register_passkey_start(
            body.email,
            display_name=body.display_name,
            request_origin=request.headers.get("origin"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/register/passkey/verify", status_code=status.HTTP_201_CREATED)
async def register_passkey_verify(
    body: PasskeyVerifyBody,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
):
    """Finish passwordless signup and set auth cookies."""
    try:
        user, access, refresh = await auth.register_passkey_finish(
            body.credential,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            request_origin=request.headers.get("origin"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_auth_cookies(response, settings, access, refresh)
    return {"user": user}


async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
):
    """Verify password and set session cookie."""
    rate_limiter.check(
        f"login:{rate_limiter.client_ip(request)}:{body.email.strip().lower()}",
        limit=10,
        window_seconds=60,
    )
    try:
        user, access, refresh = await auth.login(
            body.email,
            body.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_auth_cookies(response, settings, access, refresh)
    return {"user": user}


@router.post("/refresh")
def refresh_tokens(
    response: Response,
    refresh_token: RefreshTokenDep,
    auth: AuthServiceDep,
    settings: SettingsDep,
):
    """Issue a new access JWT using the refresh cookie (no login form needed)."""
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sign in required")
    try:
        access = auth.refresh_access_token(refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _set_access_cookie(response, settings, access)
    return {"ok": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth: AuthServiceDep,
    refresh_token: RefreshTokenDep,
    settings: SettingsDep,
):
    """Revoke refresh JWT and clear auth cookies."""
    auth.logout(refresh_token)
    _clear_auth_cookies(response, settings)
    return None


@router.get("/me")
def me(user: CurrentUserDep, auth: AuthServiceDep, settings: SettingsDep):
    """Return current user, notification emails, passkeys, and admin flag.

    ``CurrentUserDep`` loads the user from the session cookie or returns 401.
    """
    return {
        "user": {**user, "is_admin": user_is_admin(user, settings)},
        "notification_emails": auth.list_notification_emails(user["id"]),
        "passkeys": auth.list_passkeys(user["id"]),
    }


# -----------------------------------------------------------------------------
# Account email verification
# -----------------------------------------------------------------------------


@router.post("/verify-email")
async def verify_email(body: VerifyEmailBody, auth: AuthServiceDep):
    """Mark primary email verified using one-time token (no cookie required)."""
    try:
        user = await auth.verify_account_email(body.token)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user}


@router.post("/resend-verification")
async def resend_verification(user: CurrentUserDep, request: Request, auth: AuthServiceDep):
    """Resend account verification email to logged-in unverified user."""
    rate_limiter.check(
        f"resend-verify:{user['id']}",
        limit=3,
        window_seconds=3600,
    )
    try:
        await auth.resend_verification(user["id"])
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"sent": True}


# -----------------------------------------------------------------------------
# Password reset (unauthenticated) and change (authenticated)
# -----------------------------------------------------------------------------


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordBody, request: Request, auth: AuthServiceDep):
    """Request reset email. Returns whether an account matched the address."""
    rate_limiter.check(
        f"forgot:{body.email.strip().lower()}",
        limit=3,
        window_seconds=3600,
    )
    sent = await auth.forgot_password(body.email)
    return {"sent": sent}


@router.post("/reset-password")
def reset_password(body: ResetPasswordBody, auth: AuthServiceDep):
    """Set new password from email link token; invalidates all sessions."""
    try:
        auth.reset_password(body.token, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.patch("/profile")
def update_profile(body: ProfilePatchBody, user: CurrentUserDep, auth: AuthServiceDep):
    """Update display name and/or preferred theme for the logged-in user."""
    try:
        updated = auth.update_profile(
            user["id"],
            display_name=body.display_name,
            preferred_theme_id=body.preferred_theme_id,
            update_display_name=body.display_name is not None,
            update_theme=body.preferred_theme_id is not None,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": updated}


@router.post("/set-password")
def set_password(body: SetPasswordBody, user: CurrentUserDep, auth: AuthServiceDep):
    """Set an initial password for passkey-only accounts."""
    try:
        auth.set_password(user["id"], body.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/change-password")
def change_password(body: ChangePasswordBody, user: CurrentUserDep, auth: AuthServiceDep):
    """Change password while logged in; clears other sessions."""
    try:
        auth.change_password(user["id"], body.current_password, body.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# -----------------------------------------------------------------------------
# Notification emails (price alerts)
# -----------------------------------------------------------------------------


@router.get("/notification-emails")
def list_notification_emails(user: CurrentUserDep, auth: AuthServiceDep):
    """List all notification addresses on the account."""
    return auth.list_notification_emails(user["id"])


@router.post("/notification-emails", status_code=status.HTTP_201_CREATED)
async def add_notification_email(
    body: NotificationEmailCreate, user: CurrentUserDep, auth: AuthServiceDep
):
    """Add address and send verification email."""
    try:
        row = await auth.add_notification_email(user["id"], body.email, label=body.label)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.post("/notification-emails/{email_id}/verify")
async def verify_notification_email(
    email_id: int,
    body: NotificationEmailVerify,
    user: CurrentUserDep,
    auth: AuthServiceDep,
):
    """Verify notification email while logged in (path id + token in body)."""
    try:
        row = await auth.verify_notification_email_for_user(user["id"], email_id, body.token)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.post("/notification-emails/verify-public")
async def verify_notification_email_public(
    email_id: int,
    body: NotificationEmailVerify,
    request: Request,
    auth: AuthServiceDep,
):
    """Verify from email link without login (query param ``id`` + token in body)."""
    rate_limiter.check(
        f"verify-email:{rate_limiter.client_ip(request)}",
        limit=20,
        window_seconds=3600,
    )
    try:
        return await auth.verify_notification_email_public(email_id, body.token)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/notification-emails/{email_id}/resend")
async def resend_notification_email_verification(
    email_id: int, user: CurrentUserDep, auth: AuthServiceDep
):
    """Resend verification for one notification address."""
    try:
        await auth.resend_notification_email_verification(user["id"], email_id)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"sent": True}


@router.patch("/notification-emails/{email_id}/primary")
def set_primary_notification_email(
    email_id: int, user: CurrentUserDep, auth: AuthServiceDep
):
    """Set verified address as primary for default alerts."""
    try:
        return auth.set_primary_notification_email(user["id"], email_id)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/notification-emails/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_email(email_id: int, user: CurrentUserDep, auth: AuthServiceDep):
    """Remove non-primary notification email."""
    try:
        auth.delete_notification_email(user["id"], email_id)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return None


# -----------------------------------------------------------------------------
# Passkeys (WebAuthn) — two-step register and login flows
# -----------------------------------------------------------------------------
# Each flow: POST .../options → browser WebAuthn API → POST .../verify


@router.post("/passkey/register/options")
def passkey_register_options(
    request: Request, user: CurrentUserDep, auth: AuthServiceDep
):
    """Return registration challenge (logged in). Frontend calls credentials.create()."""
    return auth.passkey_registration_options(
        user, request_origin=request.headers.get("origin")
    )


@router.post("/passkey/register/verify", status_code=status.HTTP_201_CREATED)
def passkey_register_verify(
    body: PasskeyVerifyBody,
    request: Request,
    user: CurrentUserDep,
    auth: AuthServiceDep,
):
    """Save new passkey after browser completes registration."""
    try:
        return auth.verify_passkey_registration(
            user,
            body.credential,
            body.friendly_name,
            request_origin=request.headers.get("origin"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/passkey/login/options")
def passkey_login_options(
    body: PasskeyLoginOptionsBody, request: Request, auth: AuthServiceDep
):
    """Return authentication challenge. Optional email limits which passkeys appear."""
    try:
        return auth.passkey_login_options(
            body.email, request_origin=request.headers.get("origin")
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/passkey/login/verify")
def passkey_login_verify(
    body: PasskeyLoginBody,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
):
    """Verify passkey assertion and set session cookie (same as password login)."""
    try:
        user, access, refresh = auth.verify_passkey_login(
            body.credential,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            request_origin=request.headers.get("origin"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_auth_cookies(response, settings, access, refresh)
    return {"user": user}


@router.get("/passkeys")
def list_passkeys(user: CurrentUserDep, auth: AuthServiceDep):
    """List registered passkeys for account settings."""
    return auth.list_passkeys(user["id"])


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_passkey(passkey_id: int, user: CurrentUserDep, auth: AuthServiceDep):
    """Remove one passkey from the account."""
    try:
        auth.delete_passkey(user["id"], passkey_id)
    except AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None
