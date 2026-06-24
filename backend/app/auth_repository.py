"""Database layer for authentication and user-owned data.

**Where this file fits in the app**

Think of the backend as three layers that talk to each other:

1. ``auth_routes.py`` — HTTP endpoints (what the browser calls).
2. ``auth_service.py`` — business rules (validation, emails, passkey crypto).
3. **This file** — SQL reads and writes (how data is stored in PostgreSQL).

Read in that order if you are learning the login flow top-to-bottom.
This file never decides *whether* an action is allowed; it only runs queries
and returns rows as Python dictionaries.

**Security habits used here**

- Passwords arrive already hashed from ``passwords.py`` — we never store plain text.
- Session and email tokens are hashed before INSERT; the raw token is returned once
  to the caller so it can go in a cookie or email link.
- Writes use ``self.db.session()`` so concurrent requests share a thread-safe session.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.app.auth_tokens import hash_token, new_token
from backend.app.database import Database
from backend.app.db.models import (
    CatalogMeta,
    EmailVerificationToken,
    PasskeyCredential,
    PasswordResetToken,
    RefreshSession,
    User,
    UserLibrary,
    UserNotificationEmail,
    Watch,
    WebAuthnChallenge,
)
from backend.app.db.session import row_to_dict
from backend.app.db.util import as_dict, utc_now_iso


class AuthRepository:
    """Runs SQL for users, sessions, tokens, passkeys, and per-user library rows.

    Each public method maps to one or more database operations. Methods that
    change data return fresh rows when useful; simple deletes return ``None``
    or a boolean.
    """

    def __init__(self, db: Database):
        """Store a shared ``Database`` wrapper used for every query.

        Args:
            db: App-wide database helper (engine + session factory).
        """
        self.db = db

    # -------------------------------------------------------------------------
    # Users — account rows in the ``users`` table
    # -------------------------------------------------------------------------

    def create_user(
        self,
        email: str,
        password_hash: str | None,
        *,
        display_name: str | None = None,
        email_verified: bool = False,
    ) -> dict:
        """Insert a new user and their primary notification email in one transaction.

        ``password_hash`` must already be hashed — this layer never sees the raw
        password. Email is normalized (trimmed, lowercased) so lookups stay
        consistent.

        Args:
            email: Login address (stored lowercased).
            password_hash: Bcrypt/scrypt hash, or ``None`` for passkey-only accounts.
            display_name: Optional friendly name shown in the UI.
            email_verified: If True, set ``email_verified_at`` immediately.

        Returns:
            The new user row as a dict (all columns from ``SELECT *``).
        """
        now = utc_now_iso()
        normalized = email.strip().lower()
        with self.db.session() as session:
            user = User(
                email=normalized,
                password_hash=password_hash,
                display_name=display_name,
                email_verified_at=now if email_verified else None,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            session.add(
                UserNotificationEmail(
                    user_id=user.id,
                    email=normalized,
                    label="Primary",
                    verified_at=now if email_verified else None,
                    is_primary=1,
                    created_at=now,
                )
            )
            session.flush()
            return as_dict(user)

    def get_user_by_id(self, user_id: int) -> dict | None:
        """Fetch one user by primary key.

        Args:
            user_id: Integer id from the ``users`` table.

        Returns:
            User dict, or ``None`` if no row exists.
        """
        with self.db.session() as session:
            return row_to_dict(session.get(User, user_id))

    def get_user_by_email(self, email: str) -> dict | None:
        """Fetch one user by email address (case-insensitive).

        Args:
            email: Address to look up (normalized before query).

        Returns:
            User dict, or ``None`` if not found.
        """
        normalized = email.strip().lower()
        with self.db.session() as session:
            user = session.execute(
                select(User).where(User.email == normalized)
            ).scalar_one_or_none()
            return as_dict(user)

    def update_user_password(self, user_id: int, password_hash: str) -> None:
        """Replace the stored password hash for a user.

        Args:
            user_id: User to update.
            password_hash: New hash from ``hash_password()`` — never plain text.
        """
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(User)
                .where(User.id == user_id)
                .values(password_hash=password_hash, updated_at=now)
            )

    def update_user_profile(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        preferred_theme_id: str | None = None,
        update_display_name: bool = False,
        update_theme: bool = False,
    ) -> dict | None:
        """Change display name and/or preferred email theme."""
        now = utc_now_iso()
        with self.db.session() as session:
            if update_display_name:
                session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(display_name=display_name, updated_at=now)
                )
            if update_theme:
                session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(preferred_theme_id=preferred_theme_id, updated_at=now)
                )
            return row_to_dict(session.get(User, user_id))

    def mark_email_verified(self, user_id: int) -> None:
        """Set verification timestamps on the user and matching primary email row.

        Called after a valid email-verification token is consumed.
        """
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(User)
                .where(User.id == user_id)
                .values(email_verified_at=now, updated_at=now)
            )
            user = session.get(User, user_id)
            if user:
                session.execute(
                    update(UserNotificationEmail)
                    .where(
                        UserNotificationEmail.user_id == user_id,
                        UserNotificationEmail.email == user.email,
                    )
                    .values(verified_at=now)
                )

    # -------------------------------------------------------------------------
    # Refresh sessions — JWT refresh tokens (jti stored hashed in ``sessions``)
    # -------------------------------------------------------------------------

    def create_refresh_session(
        self,
        user_id: int,
        jti: str,
        *,
        ttl_days: int,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """Persist a refresh token id so logout can revoke it.

        The JWT refresh token embeds ``jti``; we store ``hash_token(jti)`` only.
        """
        now = datetime.now(UTC)
        expires = (now + timedelta(days=ttl_days)).isoformat()
        created = now.isoformat()
        with self.db.session() as session:
            refresh_session = RefreshSession(
                user_id=user_id,
                token_hash=hash_token(jti),
                expires_at=expires,
                created_at=created,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            session.add(refresh_session)
            session.flush()
            return as_dict(refresh_session)

    def get_refresh_session_by_jti(self, jti: str) -> dict | None:
        """Return session row if refresh ``jti`` is valid and not expired."""
        with self.db.session() as session:
            stmt = (
                select(
                    RefreshSession.id,
                    RefreshSession.user_id,
                    RefreshSession.token_hash,
                    RefreshSession.expires_at,
                    RefreshSession.created_at,
                    RefreshSession.user_agent,
                    RefreshSession.ip_address,
                    User.email,
                    User.display_name,
                    User.email_verified_at,
                    User.password_hash,
                    User.token_version,
                )
                .join(User, User.id == RefreshSession.user_id)
                .where(
                    RefreshSession.token_hash == hash_token(jti),
                    RefreshSession.expires_at > utc_now_iso(),
                )
            )
            return as_dict(session.execute(stmt).mappings().first())

    def delete_refresh_session_by_jti(self, jti: str) -> None:
        """Revoke one refresh token (logout)."""
        with self.db.session() as session:
            session.execute(
                delete(RefreshSession).where(RefreshSession.token_hash == hash_token(jti))
            )

    def delete_user_sessions(self, user_id: int) -> None:
        """Remove every refresh session for a user (e.g. after password change)."""
        with self.db.session() as session:
            session.execute(delete(RefreshSession).where(RefreshSession.user_id == user_id))

    def bump_token_version(self, user_id: int) -> None:
        """Invalidate outstanding access JWTs after password change or reset."""
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    token_version=func.coalesce(User.token_version, 0) + 1,
                    updated_at=now,
                )
            )

    # -------------------------------------------------------------------------
    # Account email verification — one-time links in ``email_verification_tokens``
    # -------------------------------------------------------------------------

    def create_email_verification_token(self, user_id: int, *, ttl_hours: int = 48) -> str:
        """Create a single-use token for verifying the account's primary email.

        Old tokens for the same user are deleted first so only one link is valid.

        Args:
            user_id: User who must verify.
            ttl_hours: Hours until the link expires (default 48).

        Returns:
            Raw token string to embed in the verification URL.
        """
        token = new_token()
        now = datetime.now(UTC)
        expires = (now + timedelta(hours=ttl_hours)).isoformat()
        with self.db.session() as session:
            session.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
            )
            session.add(
                EmailVerificationToken(
                    user_id=user_id,
                    token_hash=hash_token(token),
                    expires_at=expires,
                    created_at=now.isoformat(),
                )
            )
        return token

    def consume_email_verification_token(self, token: str) -> dict | None:
        """Validate a verification token and delete it (one-time use).

        "Consume" means: find row, delete row, return data — the link cannot be
        clicked twice.

        Args:
            token: Raw token from the email link query string.

        Returns:
            Token row dict (includes ``user_id``), or ``None`` if bad/expired.
        """
        with self.db.session() as session:
            row = session.execute(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.token_hash == hash_token(token),
                    EmailVerificationToken.expires_at > utc_now_iso(),
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            data = as_dict(row)
            session.delete(row)
            return data

    # -------------------------------------------------------------------------
    # Password reset — short-lived tokens in ``password_reset_tokens``
    # -------------------------------------------------------------------------

    def create_password_reset_token(self, user_id: int, *, ttl_hours: int = 2) -> str:
        """Create a password-reset link token (shorter TTL than email verify).

        Args:
            user_id: Account that requested reset.
            ttl_hours: Link lifetime in hours (default 2).

        Returns:
            Raw token for the reset URL.
        """
        token = new_token()
        now = datetime.now(UTC)
        expires = (now + timedelta(hours=ttl_hours)).isoformat()
        with self.db.session() as session:
            session.execute(
                delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
            )
            session.add(
                PasswordResetToken(
                    user_id=user_id,
                    token_hash=hash_token(token),
                    expires_at=expires,
                    created_at=now.isoformat(),
                )
            )
        return token

    def consume_password_reset_token(self, token: str) -> dict | None:
        """Validate and delete a password-reset token (one-time use).

        Args:
            token: Raw token from the reset-password page.

        Returns:
            Token row dict, or ``None`` if invalid or expired.
        """
        with self.db.session() as session:
            row = session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash == hash_token(token),
                    PasswordResetToken.expires_at > utc_now_iso(),
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            data = as_dict(row)
            session.delete(row)
            return data

    # -------------------------------------------------------------------------
    # Notification emails — extra addresses for price alerts
    # -------------------------------------------------------------------------

    def list_notification_emails(self, user_id: int) -> list[dict]:
        """List all notification emails for a user (primary first).

        ``ORDER BY is_primary DESC`` puts the main address at the top.
        """
        with self.db.session() as session:
            rows = session.execute(
                select(UserNotificationEmail)
                .where(UserNotificationEmail.user_id == user_id)
                .order_by(
                    UserNotificationEmail.is_primary.desc(),
                    UserNotificationEmail.created_at.asc(),
                )
            ).scalars().all()
            return [as_dict(row) for row in rows]

    def get_notification_email_by_id(self, email_id: int) -> dict | None:
        """Fetch a notification email by id (no user check — use with care)."""
        with self.db.session() as session:
            return row_to_dict(session.get(UserNotificationEmail, email_id))

    def get_notification_email(self, email_id: int, user_id: int) -> dict | None:
        """Fetch a notification email only if it belongs to ``user_id``."""
        with self.db.session() as session:
            row = session.execute(
                select(UserNotificationEmail).where(
                    UserNotificationEmail.id == email_id,
                    UserNotificationEmail.user_id == user_id,
                )
            ).scalar_one_or_none()
            return as_dict(row)

    def get_notification_email_by_address(self, user_id: int, email: str) -> dict | None:
        """Find a notification row by address for one user (case-insensitive)."""
        normalized = email.strip().lower()
        with self.db.session() as session:
            row = session.execute(
                select(UserNotificationEmail).where(
                    UserNotificationEmail.user_id == user_id,
                    UserNotificationEmail.email == normalized,
                )
            ).scalar_one_or_none()
            return as_dict(row)

    def add_notification_email(
        self, user_id: int, email: str, *, label: str | None = None
    ) -> dict:
        """Add a secondary notification address (unverified until user clicks link).

        Args:
            user_id: Account owner.
            email: New address (normalized).
            label: Optional note like "Work".

        Returns:
            The inserted row as a dict.
        """
        now = utc_now_iso()
        normalized = email.strip().lower()
        with self.db.session() as session:
            notification_email = UserNotificationEmail(
                user_id=user_id,
                email=normalized,
                label=label,
                verified_at=None,
                is_primary=0,
                created_at=now,
            )
            session.add(notification_email)
            session.flush()
            return as_dict(notification_email)

    def verify_notification_email(self, email_id: int, user_id: int) -> dict | None:
        """Mark one notification address as verified.

        Returns:
            Updated row, or ``None`` if id/user mismatch.
        """
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(UserNotificationEmail)
                .where(
                    UserNotificationEmail.id == email_id,
                    UserNotificationEmail.user_id == user_id,
                )
                .values(verified_at=now)
            )
            row = session.execute(
                select(UserNotificationEmail).where(
                    UserNotificationEmail.id == email_id,
                    UserNotificationEmail.user_id == user_id,
                )
            ).scalar_one_or_none()
            return as_dict(row)

    def set_primary_notification_email(self, email_id: int, user_id: int) -> dict | None:
        """Make one verified email primary; clears ``is_primary`` on all others.

        Two UPDATEs: first zero out every row for the user, then set the chosen one.
        """
        with self.db.session() as session:
            session.execute(
                update(UserNotificationEmail)
                .where(UserNotificationEmail.user_id == user_id)
                .values(is_primary=0)
            )
            session.execute(
                update(UserNotificationEmail)
                .where(
                    UserNotificationEmail.id == email_id,
                    UserNotificationEmail.user_id == user_id,
                )
                .values(is_primary=1)
            )
            row = session.execute(
                select(UserNotificationEmail).where(
                    UserNotificationEmail.id == email_id,
                    UserNotificationEmail.user_id == user_id,
                )
            ).scalar_one_or_none()
            return as_dict(row)

    def delete_notification_email(self, email_id: int, user_id: int) -> bool:
        """Delete a non-primary notification email.

        Returns:
            True if a row was deleted; False if missing or primary (protected).
        """
        with self.db.session() as session:
            row = session.execute(
                select(UserNotificationEmail.is_primary).where(
                    UserNotificationEmail.id == email_id,
                    UserNotificationEmail.user_id == user_id,
                )
            ).first()
            if row is None or row.is_primary:
                return False
            result = session.execute(
                delete(UserNotificationEmail).where(
                    UserNotificationEmail.id == email_id,
                    UserNotificationEmail.user_id == user_id,
                )
            )
            return result.rowcount > 0

    def create_notification_email_verification_token(
        self, email_id: int, *, ttl_hours: int = 48
    ) -> str:
        """Store a hashed verification token in ``catalog_meta`` (key-value table).

        Reuses ``catalog_meta`` instead of a dedicated table: key is
        ``notify_email:{email_id}``, value is JSON with hash + expiry.

        Returns:
            Raw token for the verification link.
        """
        token = new_token()
        now = datetime.now(UTC)
        expires = (now + timedelta(hours=ttl_hours)).isoformat()
        key = f"notify_email:{email_id}"
        value = json.dumps({"hash": hash_token(token), "expires": expires})
        updated_at = now.isoformat()
        with self.db.session() as session:
            stmt = pg_insert(CatalogMeta).values(key=key, value=value, updated_at=updated_at)
            stmt = stmt.on_conflict_do_update(
                index_elements=[CatalogMeta.key],
                set_={
                    "value": stmt.excluded.value,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            session.execute(stmt)
        return token

    def consume_notification_email_verification_token(
        self, email_id: int, token: str
    ) -> bool:
        """Check notification-email token and delete the meta row if valid.

        Returns:
            True if token matched and was not expired; False otherwise.
        """
        key = f"notify_email:{email_id}"
        with self.db.session() as session:
            row = session.execute(
                select(CatalogMeta.value).where(CatalogMeta.key == key)
            ).first()
            if row is None:
                return False
            payload = json.loads(row.value)
            if payload.get("expires", "") <= utc_now_iso():
                return False
            if payload.get("hash") != hash_token(token):
                return False
            session.execute(delete(CatalogMeta).where(CatalogMeta.key == key))
            return True

    # -------------------------------------------------------------------------
    # WebAuthn challenges — short-lived server secrets for passkey handshakes
    # -------------------------------------------------------------------------

    def store_webauthn_challenge(
        self, challenge: str, purpose: str, user_id: int | None, *, ttl_minutes: int = 5
    ) -> None:
        """Save a challenge string until the browser finishes passkey registration/login.

        Args:
            challenge: Base64url challenge sent to the client.
            purpose: ``"register"`` or ``"login"`` — must match on verify.
            user_id: Known user for register/login-with-email; ``None`` for discoverable login.
            ttl_minutes: Challenge lifetime (default 5 minutes).
        """
        now = datetime.now(UTC)
        expires = (now + timedelta(minutes=ttl_minutes)).isoformat()
        with self.db.session() as session:
            session.execute(
                delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at <= utc_now_iso())
            )
            session.add(
                WebAuthnChallenge(
                    challenge=challenge,
                    user_id=user_id,
                    purpose=purpose,
                    expires_at=expires,
                    created_at=now.isoformat(),
                )
            )

    def pop_webauthn_challenge(self, challenge: str, purpose: str) -> dict | None:
        """Find a challenge, delete it, and return the row (one-time use).

        "Pop" is like stack pop: read then remove so replay attacks fail.

        Returns:
            Challenge row dict, or ``None`` if missing/expired/wrong purpose.
        """
        with self.db.session() as session:
            row = session.execute(
                select(WebAuthnChallenge).where(
                    WebAuthnChallenge.challenge == challenge,
                    WebAuthnChallenge.purpose == purpose,
                    WebAuthnChallenge.expires_at > utc_now_iso(),
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            data = as_dict(row)
            session.delete(row)
            return data

    def peek_webauthn_challenge(self, challenge: str, purpose: str) -> dict | None:
        """Return a challenge row without consuming it (signup finish needs user id first)."""
        with self.db.session() as session:
            row = session.execute(
                select(WebAuthnChallenge).where(
                    WebAuthnChallenge.challenge == challenge,
                    WebAuthnChallenge.purpose == purpose,
                    WebAuthnChallenge.expires_at > utc_now_iso(),
                )
            ).scalar_one_or_none()
            return as_dict(row)

    # -------------------------------------------------------------------------
    # Passkeys — WebAuthn credentials in ``passkey_credentials``
    # -------------------------------------------------------------------------

    def create_passkey(
        self,
        user_id: int,
        credential_id: bytes,
        public_key: bytes,
        sign_count: int,
        transports: list[str] | None,
        friendly_name: str | None,
    ) -> dict:
        """Persist a new passkey after cryptographic verification in the service layer.

        Stores the public key and signature counter — never the private key
        (that stays on the user's device).

        Returns:
            Full passkey row including database ``id``.
        """
        now = utc_now_iso()
        with self.db.session() as session:
            passkey = PasskeyCredential(
                user_id=user_id,
                credential_id=credential_id,
                public_key=public_key,
                sign_count=sign_count,
                transports=json.dumps(transports or []),
                friendly_name=friendly_name,
                created_at=now,
            )
            session.add(passkey)
            session.flush()
            return as_dict(passkey)

    def list_passkey_credential_ids(self, user_id: int) -> list[bytes]:
        """Return raw credential ids for WebAuthn allow/exclude lists."""
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(PasskeyCredential.credential_id).where(
                        PasskeyCredential.user_id == user_id
                    )
                )
            )

    def list_passkeys(self, user_id: int) -> list[dict]:
        """List passkey metadata for account settings (no secret key material in SELECT)."""
        with self.db.session() as session:
            rows = session.execute(
                select(
                    PasskeyCredential.id,
                    PasskeyCredential.user_id,
                    PasskeyCredential.sign_count,
                    PasskeyCredential.transports,
                    PasskeyCredential.friendly_name,
                    PasskeyCredential.created_at,
                    PasskeyCredential.last_used_at,
                )
                .where(PasskeyCredential.user_id == user_id)
                .order_by(PasskeyCredential.created_at.desc())
            ).mappings().all()
            return [dict(row) for row in rows]

    def get_passkey_by_credential_id(self, credential_id: bytes) -> dict | None:
        """Look up a passkey by the credential id from the browser's assertion."""
        with self.db.session() as session:
            row = session.execute(
                select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id)
            ).scalar_one_or_none()
            return as_dict(row)

    def update_passkey_sign_count(self, passkey_id: int, sign_count: int) -> None:
        """Update signature counter after successful login (detects cloned keys)."""
        now = utc_now_iso()
        with self.db.session() as session:
            session.execute(
                update(PasskeyCredential)
                .where(PasskeyCredential.id == passkey_id)
                .values(sign_count=sign_count, last_used_at=now)
            )

    def delete_passkey(self, passkey_id: int, user_id: int) -> bool:
        """Remove one passkey if it belongs to the user.

        Returns:
            True if a row was deleted.
        """
        with self.db.session() as session:
            result = session.execute(
                delete(PasskeyCredential).where(
                    PasskeyCredential.id == passkey_id,
                    PasskeyCredential.user_id == user_id,
                )
            )
            return result.rowcount > 0

    def delete_all_passkeys(self, user_id: int) -> int:
        """Remove every passkey for a user (e.g. switching to password-only sign-in)."""
        with self.db.session() as session:
            result = session.execute(
                delete(PasskeyCredential).where(PasskeyCredential.user_id == user_id)
            )
            return result.rowcount

    def delete_user(self, user_id: int) -> bool:
        """Permanently delete a user account and cascaded auth data."""
        with self.db.session() as session:
            result = session.execute(delete(User).where(User.id == user_id))
            return result.rowcount > 0

    def admin_user_stats(self) -> dict:
        """User counts for the admin dashboard."""
        with self.db.session() as session:
            total = session.execute(select(func.count()).select_from(User)).scalar_one()
            verified = session.execute(
                select(func.count()).select_from(User).where(User.email_verified_at.is_not(None))
            ).scalar_one()
            with_password = session.execute(
                select(func.count()).select_from(User).where(User.password_hash.is_not(None))
            ).scalar_one()
            passkeys = session.execute(
                select(func.count()).select_from(PasskeyCredential)
            ).scalar_one()
            sessions = session.execute(
                select(func.count()).select_from(RefreshSession)
            ).scalar_one()
        return {
            "total": total,
            "verified": verified,
            "with_password": with_password,
            "passkeys": passkeys,
            "active_sessions": sessions,
        }

    def list_users_admin(
        self,
        *,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        library_count_sq = (
            select(func.count())
            .select_from(UserLibrary)
            .where(UserLibrary.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        watch_count_sq = (
            select(func.count())
            .select_from(Watch)
            .where(Watch.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        passkey_count_sq = (
            select(func.count())
            .select_from(PasskeyCredential)
            .where(PasskeyCredential.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        bounded = max(1, min(limit, 200))
        page_offset = max(0, offset)

        filters = []
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(User.email.ilike(pattern), User.display_name.ilike(pattern))
            )

        with self.db.session() as session:
            count_stmt = select(func.count()).select_from(User)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = session.execute(count_stmt).scalar_one()

            stmt = (
                select(
                    User.id,
                    User.email,
                    User.display_name,
                    User.email_verified_at,
                    User.created_at,
                    User.updated_at,
                    library_count_sq.label("library_count"),
                    watch_count_sq.label("watch_count"),
                    passkey_count_sq.label("passkey_count"),
                    (User.password_hash.is_not(None)).label("has_password"),
                )
                .order_by(User.created_at.desc())
                .limit(bounded)
                .offset(page_offset)
            )
            if filters:
                stmt = stmt.where(*filters)
            rows = session.execute(stmt).mappings().all()

            items = []
            for row in rows:
                item = dict(row)
                item["email_verified"] = bool(item.pop("email_verified_at"))
                item["has_password"] = bool(item["has_password"])
                items.append(item)
            return items, total

    def list_sessions_admin(
        self,
        *,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        bounded = max(1, min(limit, 200))
        page_offset = max(0, offset)
        filters = []
        if q and q.strip():
            filters.append(User.email.ilike(f"%{q.strip()}%"))

        with self.db.session() as session:
            count_stmt = (
                select(func.count())
                .select_from(RefreshSession)
                .join(User, User.id == RefreshSession.user_id)
            )
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = session.execute(count_stmt).scalar_one()

            stmt = (
                select(
                    RefreshSession.id,
                    RefreshSession.user_id,
                    RefreshSession.expires_at,
                    RefreshSession.created_at,
                    RefreshSession.user_agent,
                    RefreshSession.ip_address,
                    User.email.label("user_email"),
                )
                .join(User, User.id == RefreshSession.user_id)
                .order_by(RefreshSession.created_at.desc())
                .limit(bounded)
                .offset(page_offset)
            )
            if filters:
                stmt = stmt.where(*filters)
            rows = session.execute(stmt).mappings().all()
            return [dict(row) for row in rows], total

    def list_passkeys_admin(
        self,
        *,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        bounded = max(1, min(limit, 200))
        page_offset = max(0, offset)
        filters = []
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(User.email.ilike(pattern), PasskeyCredential.friendly_name.ilike(pattern))
            )

        with self.db.session() as session:
            count_stmt = (
                select(func.count())
                .select_from(PasskeyCredential)
                .join(User, User.id == PasskeyCredential.user_id)
            )
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = session.execute(count_stmt).scalar_one()

            stmt = (
                select(
                    PasskeyCredential.id,
                    PasskeyCredential.user_id,
                    PasskeyCredential.friendly_name,
                    PasskeyCredential.transports,
                    PasskeyCredential.sign_count,
                    PasskeyCredential.created_at,
                    PasskeyCredential.last_used_at,
                    User.email.label("user_email"),
                )
                .join(User, User.id == PasskeyCredential.user_id)
                .order_by(PasskeyCredential.created_at.desc())
                .limit(bounded)
                .offset(page_offset)
            )
            if filters:
                stmt = stmt.where(*filters)
            rows = session.execute(stmt).mappings().all()
            return [dict(row) for row in rows], total

    def list_notification_emails_admin(
        self,
        *,
        q: str | None = None,
        verified_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        bounded = max(1, min(limit, 200))
        page_offset = max(0, offset)
        filters = []
        if verified_only:
            filters.append(UserNotificationEmail.verified_at.is_not(None))
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(
                    UserNotificationEmail.email.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )

        with self.db.session() as session:
            count_stmt = (
                select(func.count())
                .select_from(UserNotificationEmail)
                .join(User, User.id == UserNotificationEmail.user_id)
            )
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = session.execute(count_stmt).scalar_one()

            stmt = (
                select(
                    UserNotificationEmail.id,
                    UserNotificationEmail.user_id,
                    UserNotificationEmail.email,
                    UserNotificationEmail.label,
                    UserNotificationEmail.verified_at,
                    UserNotificationEmail.is_primary,
                    UserNotificationEmail.created_at,
                    User.email.label("user_email"),
                )
                .join(User, User.id == UserNotificationEmail.user_id)
                .order_by(UserNotificationEmail.created_at.desc())
                .limit(bounded)
                .offset(page_offset)
            )
            if filters:
                stmt = stmt.where(*filters)
            rows = session.execute(stmt).mappings().all()

            items = []
            for row in rows:
                item = dict(row)
                item["verified"] = bool(item.pop("verified_at"))
                item["is_primary"] = bool(item["is_primary"])
                items.append(item)
            return items, total

    def admin_delete_passkey(self, passkey_id: int) -> bool:
        with self.db.session() as session:
            result = session.execute(
                delete(PasskeyCredential).where(PasskeyCredential.id == passkey_id)
            )
            return result.rowcount > 0

    def admin_revoke_user_sessions(self, user_id: int) -> int:
        with self.db.session() as session:
            result = session.execute(
                delete(RefreshSession).where(RefreshSession.user_id == user_id)
            )
            return result.rowcount

    # -------------------------------------------------------------------------
    # User library — which games a logged-in user has saved
    # -------------------------------------------------------------------------

    def add_to_library(self, user_id: int, game_id: int) -> None:
        """Add a game to the user's library (no-op if already present).

        ``ON CONFLICT DO NOTHING`` skips the insert when the (user_id, game_id) pair exists.
        """
        now = utc_now_iso()
        with self.db.session() as session:
            stmt = pg_insert(UserLibrary).values(
                user_id=user_id,
                game_id=game_id,
                created_at=now,
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "game_id"])
            session.execute(stmt)

    def remove_from_library(self, user_id: int, game_id: int) -> bool:
        """Remove a game from library and clear any price watches for that game.

        Returns:
            True if a library row was removed.
        """
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

    def is_in_library(self, user_id: int, game_id: int) -> bool:
        """Return whether the user has saved this game."""
        with self.db.session() as session:
            row = session.execute(
                select(UserLibrary.user_id).where(
                    UserLibrary.user_id == user_id,
                    UserLibrary.game_id == game_id,
                )
            ).first()
            return row is not None

    def library_game_ids(self, user_id: int) -> set[int]:
        """Return all game ids in the user's library as a Python set."""
        with self.db.session() as session:
            rows = session.execute(
                select(UserLibrary.game_id).where(UserLibrary.user_id == user_id)
            ).scalars().all()
            return set(rows)
