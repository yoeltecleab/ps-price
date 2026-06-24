"""Business logic for accounts, sessions, passkeys, and notification emails.

**Where this file fits in the app**

Suggested reading order for the auth feature:

1. ``auth_routes.py`` — HTTP: JSON in, cookies out.
2. **This file** — rules: validate input, call repository, send emails.
3. ``auth_repository.py`` — SQL: read/write SQLite tables.

Routes should stay thin (parse request, call service, map errors to status codes).
This service owns *what should happen*; the repository owns *how rows are stored*.

**Security ideas implemented here**

- Passwords are hashed with ``hash_password`` before storage; verification uses
  ``verify_password`` (timing-safe compare of hashes).
- Generic error messages on login/register (e.g. "invalid email or password") so
  attackers cannot tell whether an email exists.
- ``forgot_password`` always succeeds silently when email is unknown (same reason).
- Session tokens and email link tokens are created in the repository as hashes.
- Password change and reset invalidate all existing sessions.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from backend.app.auth_repository import AuthRepository
from backend.app.auth_tokens import new_token
from backend.app.config import Settings
from backend.app.jwt_tokens import (
    ACCESS_TYPE,
    REFRESH_TYPE,
    JwtError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from backend.app.notifier import EmailNotifier
from backend.app.passwords import hash_password, verify_password
from backend.app.repository import Repository
from backend.app.webauthn_config import effective_origins, effective_rp_id


logger = logging.getLogger(__name__)
# Simple regex: one @, no spaces — not perfect but fast for first-pass validation.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 10


class AuthError(ValueError):
    """Raised when auth input or state is invalid.

    Routes catch this and turn it into HTTP 400/401 with a safe message string.
    """


class AuthService:
    """Coordinates registration, login, verification, passkeys, and profile APIs.

    Dependencies are injected in ``__init__`` so tests can swap fakes:
    settings, auth_repo, main repo, and email notifier.
    """

    # Cookie names shared with ``auth_routes`` — must match on set and read.
    ACCESS_COOKIE = "ps_price_access"
    REFRESH_COOKIE = "ps_price_refresh"

    def __init__(
        self,
        settings: Settings,
        auth_repo: AuthRepository,
        repo: Repository,
        notifier: EmailNotifier,
    ):
        """Wire up config, database access, catalog repo, and outbound email.

        Args:
            settings: App config (URLs, WebAuthn RP id, session TTL, etc.).
            auth_repo: User/session/token SQL layer.
            repo: General game/catalog repository (shared with rest of app).
            notifier: Sends verification and reset emails.
        """
        self.settings = settings
        self.auth_repo = auth_repo
        self.repo = repo
        self.notifier = notifier

    # -------------------------------------------------------------------------
    # Internal helpers — validation and safe user shapes
    # -------------------------------------------------------------------------

    def _validate_email(self, email: str) -> str:
        """Normalize and check email format.

        Args:
            email: Raw string from the client.

        Returns:
            Lowercased, trimmed email.

        Raises:
            AuthError: If the format does not match ``EMAIL_RE``.
        """
        normalized = email.strip().lower()
        if not EMAIL_RE.match(normalized):
            raise AuthError("email is invalid")
        return normalized

    def _validate_password(self, password: str) -> None:
        """Enforce minimum length before hashing.

        Raises:
            AuthError: If password is shorter than ``MIN_PASSWORD_LEN``.
        """
        if len(password) < MIN_PASSWORD_LEN:
            raise AuthError(f"password must be at least {MIN_PASSWORD_LEN} characters")

    def _user_public(self, user: dict) -> dict:
        """Strip sensitive fields before returning user JSON to the browser.

        Never expose ``password_hash`` — only ``has_password`` boolean.

        Args:
            user: Full user row from the database.

        Returns:
            Public-safe dict for API responses.
        """
        return {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
            "email_verified": bool(user.get("email_verified_at")),
            "has_password": bool(user.get("password_hash")),
            "preferred_theme_id": user.get("preferred_theme_id"),
            "created_at": user["created_at"],
        }

    def _issue_tokens(
        self,
        user: dict,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, str]:
        """Create access + refresh JWT pair and persist refresh ``jti`` in SQLite."""
        jti = new_token()
        self.auth_repo.create_refresh_session(
            user["id"],
            jti,
            ttl_days=self.settings.jwt_refresh_ttl_days,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        access = create_access_token(self.settings, user)
        refresh = create_refresh_token(self.settings, user["id"], jti)
        return access, refresh

    # -------------------------------------------------------------------------
    # Registration and password login
    # -------------------------------------------------------------------------

    async def register(
        self,
        email: str,
        password: str | None,
        *,
        display_name: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[dict, str, str]:
        """Create account with optional password (passkey-only accounts use password=None)."""
        normalized = self._validate_email(email)
        if self.auth_repo.get_user_by_email(normalized):
            raise AuthError("unable to create account with these details")
        if password is None:
            raise AuthError("use passkey sign-up or provide a password")
        self._validate_password(password)
        password_hash = hash_password(password)
        user = self.auth_repo.create_user(
            normalized,
            password_hash,
            display_name=display_name,
            email_verified=False,
        )
        await self._send_account_verification(user)
        access, refresh = self._issue_tokens(
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return self._user_public(user), access, refresh

    async def register_passkey_start(
        self,
        email: str,
        *,
        display_name: str | None = None,
        request_origin: str | None = None,
    ) -> dict[str, Any]:
        """Create a passwordless account and return WebAuthn registration options."""
        normalized = self._validate_email(email)
        if self.auth_repo.get_user_by_email(normalized):
            raise AuthError("unable to create account with these details")
        user = self.auth_repo.create_user(
            normalized,
            None,
            display_name=display_name,
            email_verified=False,
        )
        await self._send_account_verification(user)
        session_user = {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or display_name,
        }
        return self.passkey_registration_options(session_user, request_origin=request_origin)

    async def register_passkey_finish(
        self,
        credential: dict[str, Any],
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
        request_origin: str | None = None,
    ) -> tuple[dict, str, str]:
        """Complete passwordless signup after the browser creates a passkey."""
        client_data_b64 = credential.get("response", {}).get("clientDataJSON")
        if not client_data_b64:
            raise AuthError("invalid passkey response")
        client_payload = json.loads(base64url_to_bytes(client_data_b64).decode("utf-8"))
        challenge = client_payload.get("challenge")
        stored = self.auth_repo.peek_webauthn_challenge(challenge, "register")
        if not stored or not stored.get("user_id"):
            raise AuthError("passkey challenge expired")
        user = self.auth_repo.get_user_by_id(stored["user_id"])
        if not user:
            raise AuthError("user not found")
        session_user = {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
        }
        self.verify_passkey_registration(
            session_user,
            credential,
            "Passkey",
            request_origin=request_origin,
        )
        access, refresh = self._issue_tokens(
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return self._user_public(user), access, refresh

    async def login(
        self,
        email: str,
        password: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[dict, str, str]:
        """Verify email/password and issue JWT access + refresh tokens."""
        normalized = self._validate_email(email)
        user = self.auth_repo.get_user_by_email(normalized)
        if not user or not verify_password(password, user.get("password_hash")):
            raise AuthError("invalid email or password")
        access, refresh = self._issue_tokens(
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return self._user_public(user), access, refresh

    def logout(self, refresh_token: str | None) -> None:
        """Revoke refresh JWT by deleting its ``jti`` row (idempotent)."""
        if not refresh_token:
            return
        try:
            payload = decode_token(self.settings, refresh_token, expected_type=REFRESH_TYPE)
        except JwtError:
            return
        jti = payload.get("jti")
        if jti:
            self.auth_repo.delete_refresh_session_by_jti(jti)

    def refresh_access_token(self, refresh_token: str) -> str:
        """Validate refresh JWT and return a new short-lived access JWT."""
        payload = decode_token(self.settings, refresh_token, expected_type=REFRESH_TYPE)
        jti = payload.get("jti")
        if not jti:
            raise AuthError("invalid token")
        session = self.auth_repo.get_refresh_session_by_jti(jti)
        if not session:
            raise AuthError("invalid token")
        user = self.auth_repo.get_user_by_id(int(payload["sub"]))
        if not user:
            raise AuthError("invalid token")
        return create_access_token(self.settings, user)

    def get_user_from_access_token(self, access_token: str | None) -> dict | None:
        """Verify access JWT and return user dict for ``deps.py``."""
        if not access_token:
            return None
        try:
            payload = decode_token(self.settings, access_token, expected_type=ACCESS_TYPE)
        except JwtError:
            return None
        user_id = int(payload["sub"])
        user = self.auth_repo.get_user_by_id(user_id)
        if not user:
            return None
        if int(payload.get("ver", 0)) != int(user.get("token_version") or 0):
            return None
        return {
            "id": user_id,
            "email": user["email"],
            "display_name": user.get("display_name"),
            "email_verified": bool(user.get("email_verified_at")),
            "has_password": bool(user.get("password_hash")),
            "preferred_theme_id": user.get("preferred_theme_id"),
        }

    # Backward-compatible alias used during migration of call sites.
    def get_user_from_session(self, access_token: str | None) -> dict | None:
        return self.get_user_from_access_token(access_token)

    # -------------------------------------------------------------------------
    # Account email verification
    # -------------------------------------------------------------------------

    async def verify_account_email(self, token: str) -> dict:
        """Consume email verification link and mark the account verified.

        Args:
            token: One-time token from the verification URL.

        Returns:
            Updated public user dict.

        Raises:
            AuthError: Invalid/expired token or missing user.
        """
        row = self.auth_repo.consume_email_verification_token(token)
        if not row:
            raise AuthError("verification link is invalid or expired")
        self.auth_repo.mark_email_verified(row["user_id"])
        user = self.auth_repo.get_user_by_id(row["user_id"])
        if not user:
            raise AuthError("user not found")
        return self._user_public(user)

    async def resend_verification(self, user_id: int) -> None:
        """Send another account verification email to a logged-in user.

        Raises:
            AuthError: Unknown user or already verified.
        """
        user = self.auth_repo.get_user_by_id(user_id)
        if not user:
            raise AuthError("user not found")
        if user.get("email_verified_at"):
            raise AuthError("email is already verified")
        await self._send_account_verification(user)

    # -------------------------------------------------------------------------
    # Password reset and change
    # -------------------------------------------------------------------------

    async def forgot_password(self, email: str) -> None:
        """Email a reset link if the account exists; otherwise do nothing.

        Intentionally no error when email is unknown — prevents account enumeration.
        """
        normalized = self._validate_email(email)
        user = self.auth_repo.get_user_by_email(normalized)
        if not user:
            return
        token = self.auth_repo.create_password_reset_token(user["id"])
        link = f"{self.settings.frontend_url.rstrip('/')}/auth/reset-password?token={token}"
        theme = user.get("preferred_theme_id") or "abyss"
        from backend.app.email_templates import system_email_html

        await self.notifier.send_system_email(
            normalized,
            "Reset your PS Prices password",
            f"Reset your PS Prices password (expires in 2 hours):\n\n{link}",
            html_body=system_email_html(
                theme_id=theme,
                title="Reset your password",
                message="We received a request to reset your password. If you did not ask for this, you can ignore this email.",
                cta_label="Reset password",
                cta_href=link,
            ),
            user_id=user["id"],
            theme_id=theme,
        )

    def reset_password(self, token: str, new_password: str) -> None:
        """Set a new password from a reset link and log out all sessions.

        Args:
            token: One-time token from forgot-password email.
            new_password: New plain password (hashed before save).

        Raises:
            AuthError: Invalid token or weak password.
        """
        self._validate_password(new_password)
        row = self.auth_repo.consume_password_reset_token(token)
        if not row:
            raise AuthError("reset link is invalid or expired")
        self.auth_repo.update_user_password(row["user_id"], hash_password(new_password))
        self.auth_repo.bump_token_version(row["user_id"])
        self.auth_repo.delete_user_sessions(row["user_id"])

    def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        """Change password while logged in; requires current password.

        Bumps ``token_version`` and clears refresh sessions so old JWTs stop working.
        """
        user = self.auth_repo.get_user_by_id(user_id)
        if not user:
            raise AuthError("user not found")
        if not verify_password(current_password, user.get("password_hash")):
            raise AuthError("current password is incorrect")
        self._validate_password(new_password)
        self.auth_repo.update_user_password(user_id, hash_password(new_password))
        self.auth_repo.bump_token_version(user_id)
        self.auth_repo.delete_user_sessions(user_id)

    def set_password(self, user_id: int, new_password: str) -> None:
        """Set an initial password for passkey-only accounts."""
        user = self.auth_repo.get_user_by_id(user_id)
        if not user:
            raise AuthError("user not found")
        if user.get("password_hash"):
            raise AuthError("password already set — use change password")
        self._validate_password(new_password)
        self.auth_repo.update_user_password(user_id, hash_password(new_password))

    def update_profile(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        preferred_theme_id: str | None = None,
        update_display_name: bool = False,
        update_theme: bool = False,
    ) -> dict:
        """Update display name and/or preferred UI/email theme."""
        user = self.auth_repo.update_user_profile(
            user_id,
            display_name=display_name,
            preferred_theme_id=preferred_theme_id,
            update_display_name=update_display_name,
            update_theme=update_theme,
        )
        if not user:
            raise AuthError("user not found")
        return self._user_public(user)

    # -------------------------------------------------------------------------
    # Notification emails (price alerts)
    # -------------------------------------------------------------------------

    def list_notification_emails(self, user_id: int) -> list[dict]:
        """List notification addresses with API-friendly field names."""
        return [
            {
                "id": row["id"],
                "email": row["email"],
                "label": row.get("label"),
                "verified": bool(row.get("verified_at")),
                "is_primary": bool(row.get("is_primary")),
                "created_at": row["created_at"],
            }
            for row in self.auth_repo.list_notification_emails(user_id)
        ]

    async def add_notification_email(
        self, user_id: int, email: str, *, label: str | None = None
    ) -> dict:
        """Add an extra alert address and send a verification email.

        Returns:
            New row dict with ``verified: False``.

        Raises:
            AuthError: Duplicate address on this account.
        """
        normalized = self._validate_email(email)
        if self.auth_repo.get_notification_email_by_address(user_id, normalized):
            raise AuthError("this email is already on your account")
        row = self.auth_repo.add_notification_email(user_id, normalized, label=label)
        await self._send_notification_email_verification(user_id, row)
        return {
            "id": row["id"],
            "email": row["email"],
            "label": row.get("label"),
            "verified": False,
            "is_primary": bool(row.get("is_primary")),
            "created_at": row["created_at"],
        }

    async def verify_notification_email_public(self, email_id: int, token: str) -> dict:
        """Verify a notification email from a link (no login required).

        Used when the user clicks the link in their inbox before signing in.
        """
        if not self.auth_repo.consume_notification_email_verification_token(email_id, token):
            raise AuthError("verification link is invalid or expired")
        row = self.auth_repo.get_notification_email_by_id(email_id)
        if not row:
            raise AuthError("notification email not found")
        verified = self.auth_repo.verify_notification_email(email_id, row["user_id"])
        if not verified:
            raise AuthError("notification email not found")
        return {
            "id": verified["id"],
            "email": verified["email"],
            "label": verified.get("label"),
            "verified": True,
            "is_primary": bool(verified.get("is_primary")),
            "created_at": verified["created_at"],
        }

    async def verify_notification_email_for_user(
        self, user_id: int, email_id: int, token: str
    ) -> dict:
        """Verify a notification email while logged in (token + ownership check)."""
        if not self.auth_repo.consume_notification_email_verification_token(email_id, token):
            raise AuthError("verification link is invalid or expired")
        row = self.auth_repo.verify_notification_email(email_id, user_id)
        if not row:
            raise AuthError("notification email not found")
        return {
            "id": row["id"],
            "email": row["email"],
            "label": row.get("label"),
            "verified": True,
            "is_primary": bool(row.get("is_primary")),
            "created_at": row["created_at"],
        }

    async def resend_notification_email_verification(self, user_id: int, email_id: int) -> None:
        """Resend verification for one notification address."""
        row = self.auth_repo.get_notification_email(email_id, user_id)
        if not row:
            raise AuthError("notification email not found")
        if row.get("verified_at"):
            raise AuthError("email is already verified")
        await self._send_notification_email_verification(user_id, row)

    def set_primary_notification_email(self, user_id: int, email_id: int) -> dict:
        """Mark one verified address as primary for default alerts.

        Raises:
            AuthError: Unknown row or not verified yet.
        """
        row = self.auth_repo.get_notification_email(email_id, user_id)
        if not row:
            raise AuthError("notification email not found")
        if not row.get("verified_at"):
            raise AuthError("verify this email before setting it as primary")
        updated = self.auth_repo.set_primary_notification_email(email_id, user_id)
        if not updated:
            raise AuthError("notification email not found")
        return {
            "id": updated["id"],
            "email": updated["email"],
            "label": updated.get("label"),
            "verified": True,
            "is_primary": True,
            "created_at": updated["created_at"],
        }

    def delete_notification_email(self, user_id: int, email_id: int) -> None:
        """Remove a non-primary notification email."""
        if not self.auth_repo.delete_notification_email(email_id, user_id):
            raise AuthError("cannot delete primary or unknown notification email")

    # -------------------------------------------------------------------------
    # Passkeys (WebAuthn) — passwordless login
    # -------------------------------------------------------------------------

    def passkey_registration_options(
        self, user: dict, *, request_origin: str | None = None
    ) -> dict[str, Any]:
        """Step 1 of adding a passkey: return options for ``navigator.credentials.create``.

        Excludes credential ids already registered so the same passkey is not added twice.
        Stores the server challenge in the database for step 2.

        Args:
            user: Current logged-in user dict from session.

        Returns:
            JSON-serializable WebAuthn registration options for the frontend.
        """
        exclude: list[PublicKeyCredentialDescriptor] = []
        with self.auth_repo.db.connect() as conn:
            rows = conn.execute(
                "SELECT credential_id FROM passkey_credentials WHERE user_id = ?",
                (user["id"],),
            ).fetchall()
        exclude = [PublicKeyCredentialDescriptor(id=row["credential_id"]) for row in rows]
        rp_id = effective_rp_id(self.settings)
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=self.settings.webauthn_rp_name,
            user_id=str(user["id"]).encode(),
            user_name=user["email"],
            user_display_name=user.get("display_name") or user["email"],
            exclude_credentials=exclude or None,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        self.auth_repo.store_webauthn_challenge(
            bytes_to_base64url(options.challenge),
            "register",
            user["id"],
        )
        return self._serialize_registration_options(options)

    def verify_passkey_registration(
        self,
        user: dict,
        credential: dict[str, Any],
        friendly_name: str | None,
        *,
        request_origin: str | None = None,
    ) -> dict:
        """Step 2 of registration: verify browser response and save public key.

        Args:
            user: Logged-in user.
            credential: Payload from the browser WebAuthn API.
            friendly_name: Label shown in account settings.

        Returns:
            New passkey metadata (id, name, created_at).

        Raises:
            AuthError: Bad payload, expired challenge, or crypto failure.
        """
        client_data_b64 = credential.get("response", {}).get("clientDataJSON")
        if not client_data_b64:
            raise AuthError("invalid passkey response")
        client_payload = json.loads(base64url_to_bytes(client_data_b64).decode("utf-8"))
        challenge = client_payload.get("challenge")
        stored = self.auth_repo.pop_webauthn_challenge(challenge, "register")
        if not stored or stored.get("user_id") != user["id"]:
            raise AuthError("passkey challenge expired")

        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=effective_rp_id(self.settings),
            expected_origin=effective_origins(self.settings, request_origin),
            require_user_verification=True,
        )
        row = self.auth_repo.create_passkey(
            user["id"],
            verification.credential_id,
            verification.credential_public_key,
            verification.sign_count,
            None,
            friendly_name or "Passkey",
        )
        return {
            "id": row["id"],
            "friendly_name": row.get("friendly_name"),
            "created_at": row["created_at"],
        }

    def passkey_login_options(
        self, email: str | None = None, *, request_origin: str | None = None
    ) -> dict[str, Any]:
        """Step 1 of passkey login: authentication options for ``navigator.credentials.get``.

        If email is provided and found, ``allowCredentials`` limits to that user's passkeys.
        If email is omitted, the client may use a discoverable (resident) passkey.

        Returns:
            JSON WebAuthn authentication options including ``challenge``.
        """
        allow_credentials = None
        user_id = None
        if email:
            normalized = self._validate_email(email)
            user = self.auth_repo.get_user_by_email(normalized)
            if user:
                user_id = user["id"]
                allow_credentials = self._credential_descriptors(user_id)
        options = generate_authentication_options(
            rp_id=effective_rp_id(self.settings),
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        self.auth_repo.store_webauthn_challenge(
            bytes_to_base64url(options.challenge),
            "login",
            user_id,
        )
        return self._serialize_authentication_options(options)

    def verify_passkey_login(
        self,
        credential: dict[str, Any],
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
        request_origin: str | None = None,
    ) -> tuple[dict, str, str]:
        """Step 2 of passkey login: verify signature and issue JWTs."""
        raw_id = credential.get("rawId") or credential.get("id")
        if not raw_id:
            raise AuthError("invalid passkey response")
        credential_id = base64url_to_bytes(raw_id)
        stored_cred = self.auth_repo.get_passkey_by_credential_id(credential_id)
        if not stored_cred:
            raise AuthError("passkey not recognized")

        client_data_b64 = credential.get("response", {}).get("clientDataJSON")
        client_data = json.loads(base64url_to_bytes(client_data_b64).decode("utf-8"))
        challenge = client_data.get("challenge")
        stored = self.auth_repo.pop_webauthn_challenge(challenge, "login")
        if not stored:
            raise AuthError("passkey challenge expired")

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=effective_rp_id(self.settings),
            expected_origin=effective_origins(self.settings, request_origin),
            credential_public_key=stored_cred["public_key"],
            credential_current_sign_count=stored_cred["sign_count"],
            require_user_verification=True,
        )
        self.auth_repo.update_passkey_sign_count(stored_cred["id"], verification.new_sign_count)
        user = self.auth_repo.get_user_by_id(stored_cred["user_id"])
        if not user:
            raise AuthError("user not found")
        access, refresh = self._issue_tokens(
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return self._user_public(user), access, refresh

    def list_passkeys(self, user_id: int) -> list[dict]:
        """Return passkey metadata for the account page."""
        return self.auth_repo.list_passkeys(user_id)

    def delete_passkey(self, user_id: int, passkey_id: int) -> None:
        """Remove one passkey credential from the account."""
        if not self.auth_repo.delete_passkey(passkey_id, user_id):
            raise AuthError("passkey not found")

    def _credential_descriptors(self, user_id: int) -> list[PublicKeyCredentialDescriptor]:
        """Build WebAuthn allow-list entries from stored credential ids."""
        with self.auth_repo.db.connect() as conn:
            rows = conn.execute(
                "SELECT credential_id FROM passkey_credentials WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return [PublicKeyCredentialDescriptor(id=row["credential_id"]) for row in rows]

    def _serialize_registration_options(self, options) -> dict[str, Any]:
        """Convert library WebAuthn options to JSON the browser understands (base64url)."""
        rp_id = effective_rp_id(self.settings)
        payload: dict[str, Any] = {
            "challenge": bytes_to_base64url(options.challenge),
            "timeout": options.timeout or 120000,
            "rpId": rp_id,
            "rp": {"name": options.rp.name, "id": rp_id},
            "user": {
                "id": bytes_to_base64url(options.user.id),
                "name": options.user.name,
                "displayName": options.user.display_name,
            },
            "pubKeyCredParams": [
                {"type": "public-key", "alg": p.alg} for p in options.pub_key_cred_params
            ],
            "authenticatorSelection": {
                "residentKey": options.authenticator_selection.resident_key.value,
                "userVerification": options.authenticator_selection.user_verification.value,
            },
            "excludeCredentials": [
                {
                    "type": "public-key",
                    "id": bytes_to_base64url(c.id),
                    "transports": list(c.transports or []),
                }
                for c in (options.exclude_credentials or [])
            ],
        }
        return payload

    def _serialize_authentication_options(self, options) -> dict[str, Any]:
        """Convert authentication options to a minimal JSON dict for the frontend."""
        payload: dict[str, Any] = {
            "challenge": bytes_to_base64url(options.challenge),
            "timeout": options.timeout or 120000,
            "rpId": effective_rp_id(self.settings),
            "userVerification": options.user_verification.value,
        }
        if options.allow_credentials:
            payload["allowCredentials"] = [
                {
                    "type": "public-key",
                    "id": bytes_to_base64url(c.id),
                    "transports": list(c.transports or []),
                }
                for c in options.allow_credentials
            ]
        return payload

    # -------------------------------------------------------------------------
    # Outbound email helpers
    # -------------------------------------------------------------------------

    async def _send_account_verification(self, user: dict) -> None:
        """Create verification token and email link to ``/auth/verify``."""
        from backend.app.email_templates import system_email_html

        token = self.auth_repo.create_email_verification_token(user["id"])
        link = f"{self.settings.frontend_url.rstrip('/')}/auth/verify?token={token}"
        theme = user.get("preferred_theme_id") or "abyss"
        await self.notifier.send_system_email(
            user["email"],
            "Verify your PS Prices account",
            f"Welcome to PS Prices! Tap the button in this email to verify your account and unlock price alerts.\n\n{link}",
            html_body=system_email_html(
                theme_id=theme,
                title="Verify your email",
                message="Welcome to PS Prices. Confirm your email to track games, deploy price watches, and receive alerts in your chosen theme.",
                cta_label="Verify email",
                cta_href=link,
            ),
            user_id=user["id"],
            theme_id=theme,
        )

    async def _send_notification_email_verification(self, user_id: int, row: dict) -> None:
        """Create per-address token and email link to notification verify page."""
        from backend.app.email_templates import system_email_html

        user = self.auth_repo.get_user_by_id(user_id)
        theme = (user or {}).get("preferred_theme_id") or "abyss"
        token = self.auth_repo.create_notification_email_verification_token(row["id"])
        link = (
            f"{self.settings.frontend_url.rstrip('/')}/account/emails/verify"
            f"?id={row['id']}&token={token}"
        )
        await self.notifier.send_system_email(
            row["email"],
            "Confirm your PS Prices alert email",
            f"Confirm this address for price alerts:\n\n{link}",
            html_body=system_email_html(
                theme_id=theme,
                title="Confirm alert email",
                message="Add this address to your PS Prices account to receive price-drop notifications.",
                cta_label="Verify email",
                cta_href=link,
            ),
            user_id=user_id,
            theme_id=theme,
        )

    def require_verified_notification_email(
        self, user_id: int, notification_email_id: int | None, fallback_email: str | None
    ) -> tuple[str, int | None]:
        """Pick a verified email address for price-watch notifications.

        Used by other features (watches) so alerts only go to confirmed addresses.

        Args:
            user_id: Account owner.
            notification_email_id: Explicit id from the client, if any.
            fallback_email: Legacy/alternate email string from the client.

        Returns:
            ``(email_address, notification_email_id_or_none)``.

        Raises:
            AuthError: No verified address available.
        """
        if notification_email_id is not None:
            row = self.auth_repo.get_notification_email(notification_email_id, user_id)
            if not row:
                raise AuthError("notification email not found")
            if not row.get("verified_at"):
                raise AuthError("notification email is not verified")
            return row["email"], row["id"]
        if fallback_email:
            normalized = self._validate_email(fallback_email)
            row = self.auth_repo.get_notification_email_by_address(user_id, normalized)
            if row and row.get("verified_at"):
                return row["email"], row["id"]
            raise AuthError("use a verified notification email from your account")
        primary = next(
            (
                r
                for r in self.auth_repo.list_notification_emails(user_id)
                if r.get("is_primary") and r.get("verified_at")
            ),
            None,
        )
        if primary:
            return primary["email"], primary["id"]
        raise AuthError("verify your account email before creating watches")
