"""FastAPI dependencies for authentication and shared request context.

Authentication uses **JWT** (JSON Web Tokens):

- **Access token** — short-lived; sent on each API request via the
  ``ps_price_access`` HttpOnly cookie or ``Authorization: Bearer`` header.
- **Refresh token** — long-lived; ``ps_price_refresh`` cookie only; used at
  ``POST /api/auth/refresh`` to obtain a new access token.

Dependency chain for ``VerifiedUserDep``:
  access JWT → verify signature + version → require login → require verified email
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from backend.app.auth_service import AuthService
from backend.app.config import Settings


def _auth_service(request: Request) -> AuthService:
    """Return the AuthService instance created at application startup."""
    return request.app.state.auth_service


def _settings(request: Request) -> Settings:
    """Return the Settings instance created at application startup."""
    return request.app.state.settings


AuthServiceDep = Annotated[AuthService, Depends(_auth_service)]
SettingsDep = Annotated[Settings, Depends(_settings)]


def access_token_dep(
    ps_price_access: str | None = Cookie(default=None, alias="ps_price_access"),
    authorization: str | None = Header(default=None),
) -> str | None:
    """Read access JWT from cookie or ``Authorization: Bearer`` header."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return ps_price_access


AccessTokenDep = Annotated[str | None, Depends(access_token_dep)]


def refresh_token_dep(
    ps_price_refresh: str | None = Cookie(default=None, alias="ps_price_refresh"),
) -> str | None:
    """Read refresh JWT from HttpOnly cookie."""
    return ps_price_refresh


RefreshTokenDep = Annotated[str | None, Depends(refresh_token_dep)]

# Legacy name used by a few routes during transition.
SessionTokenDep = RefreshTokenDep


def optional_user_dep(
    auth: AuthServiceDep,
    token: AccessTokenDep,
) -> dict | None:
    """Return user dict if access JWT is valid, else None (not an error)."""
    return auth.get_user_from_access_token(token)


OptionalUserDep = Annotated[dict | None, Depends(optional_user_dep)]


def require_user_dep(
    auth: AuthServiceDep,
    token: AccessTokenDep,
) -> dict:
    """Require a signed-in user; raise 401 otherwise."""
    user = auth.get_user_from_access_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sign in required")
    return user


CurrentUserDep = Annotated[dict, Depends(require_user_dep)]


def require_verified_user_dep(
    user: CurrentUserDep,
    settings: SettingsDep,
) -> dict:
    """Require login plus verified email (library, watches, etc.)."""
    if settings.require_email_verification and not user.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="verify your email to use this feature",
        )
    return user


VerifiedUserDep = Annotated[dict, Depends(require_verified_user_dep)]


def require_admin_user_dep(
    user: VerifiedUserDep,
    settings: SettingsDep,
) -> dict:
    """Require verified user whose email is in the admin allow-list."""
    admins = settings.admin_email_list
    if not admins or user.get("email", "").lower() not in admins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin access required",
        )
    return user


AdminUserDep = Annotated[dict, Depends(require_admin_user_dep)]
