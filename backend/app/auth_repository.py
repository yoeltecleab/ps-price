"""Database layer for authentication and user-owned data.

**Where this file fits in the app**

Think of the backend as three layers that talk to each other:

1. ``auth_routes.py`` — HTTP endpoints (what the browser calls).
2. ``auth_service.py`` — business rules (validation, emails, passkey crypto).
3. **This file** — SQL reads and writes (how data is stored in SQLite).

Read in that order if you are learning the login flow top-to-bottom.
This file never decides *whether* an action is allowed; it only runs queries
and returns rows as Python dictionaries.

**Security habits used here**

- Passwords arrive already hashed from ``passwords.py`` — we never store plain text.
- Session and email tokens are hashed before INSERT; the raw token is returned once
  to the caller so it can go in a cookie or email link.
- Writes use ``self.db._lock`` so two requests do not corrupt the same rows at once.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.app.auth_tokens import hash_token, new_token
from backend.app.database import Database, row_to_dict
from backend.app.repository import utc_now_iso


class AuthRepository:
    """Runs SQL for users, sessions, tokens, passkeys, and per-user library rows.

    Each public method maps to one or more database operations. Methods that
    change data return fresh rows when useful; simple deletes return ``None``
    or a boolean.
    """

    def __init__(self, db: Database):
        """Store a shared ``Database`` wrapper used for every query.

        Args:
            db: App-wide database helper (connection + lock).
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
        # ``with self.db._lock`` = only one writer at a time for this database.
        # ``?`` placeholders are parameterized queries — values are escaped safely.
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (email, password_hash, display_name, email_verified_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    password_hash,
                    display_name,
                    now if email_verified else None,
                    now,
                    now,
                ),
            )
            user_id = cursor.lastrowid  # SQLite auto-increment id for the new row
            # Every user gets a "Primary" notification email row (for price alerts).
            conn.execute(
                """
                INSERT INTO user_notification_emails (user_id, email, label, verified_at, is_primary, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    user_id,
                    normalized,
                    "Primary",
                    now if email_verified else None,
                    now,
                ),
            )
            return dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def get_user_by_id(self, user_id: int) -> dict | None:
        """Fetch one user by primary key.

        Args:
            user_id: Integer id from the ``users`` table.

        Returns:
            User dict, or ``None`` if no row exists.
        """
        with self.db.connect() as conn:
            return row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def get_user_by_email(self, email: str) -> dict | None:
        """Fetch one user by email address (case-insensitive).

        ``COLLATE NOCASE`` tells SQLite to compare emails without caring about
        upper vs lower case.

        Args:
            email: Address to look up (normalized before query).

        Returns:
            User dict, or ``None`` if not found.
        """
        with self.db.connect() as conn:
            return row_to_dict(
                conn.execute(
                    "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                    (email.strip().lower(),),
                ).fetchone()
            )

    def update_user_password(self, user_id: int, password_hash: str) -> None:
        """Replace the stored password hash for a user.

        Args:
            user_id: User to update.
            password_hash: New hash from ``hash_password()`` — never plain text.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, now, user_id),
            )

    def update_user_profile(self, user_id: int, *, display_name: str | None) -> dict | None:
        """Change display name and return the updated user row.

        Args:
            user_id: User to update.
            display_name: New name, or ``None`` to clear it.

        Returns:
            Updated user dict, or ``None`` if the id does not exist.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                "UPDATE users SET display_name = ?, updated_at = ? WHERE id = ?",
                (display_name, now, user_id),
            )
            return row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def mark_email_verified(self, user_id: int) -> None:
        """Set verification timestamps on the user and matching primary email row.

        Called after a valid email-verification token is consumed.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                "UPDATE users SET email_verified_at = ?, updated_at = ? WHERE id = ?",
                (now, now, user_id),
            )
            user = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
            if user:
                conn.execute(
                    """
                    UPDATE user_notification_emails
                    SET verified_at = ?
                    WHERE user_id = ? AND email = ? COLLATE NOCASE
                    """,
                    (now, user_id, user["email"]),
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
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sessions (user_id, token_hash, expires_at, created_at, user_agent, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, hash_token(jti), expires, created, user_agent, ip_address),
            )
            return dict(
                conn.execute("SELECT * FROM sessions WHERE id = ?", (cursor.lastrowid,)).fetchone()
            )

    def get_refresh_session_by_jti(self, jti: str) -> dict | None:
        """Return session row if refresh ``jti`` is valid and not expired."""
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT s.*, u.email, u.display_name, u.email_verified_at, u.password_hash, u.token_version
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (hash_token(jti), utc_now_iso()),
            ).fetchone()
            return dict(row) if row else None

    def delete_refresh_session_by_jti(self, jti: str) -> None:
        """Revoke one refresh token (logout)."""
        with self.db._lock, self.db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(jti),))

    def delete_user_sessions(self, user_id: int) -> None:
        """Remove every refresh session for a user (e.g. after password change)."""
        with self.db._lock, self.db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def bump_token_version(self, user_id: int) -> None:
        """Invalidate outstanding access JWTs after password change or reset."""
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET token_version = COALESCE(token_version, 0) + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, user_id),
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
        with self.db._lock, self.db.connect() as conn:
            conn.execute("DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,))
            conn.execute(
                """
                INSERT INTO email_verification_tokens (user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, hash_token(token), expires, now.isoformat()),
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
        with self.db._lock, self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM email_verification_tokens
                WHERE token_hash = ? AND expires_at > ?
                """,
                (hash_token(token), utc_now_iso()),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "DELETE FROM email_verification_tokens WHERE id = ?",
                (row["id"],),
            )
            return dict(row)

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
        with self.db._lock, self.db.connect() as conn:
            conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
            conn.execute(
                """
                INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, hash_token(token), expires, now.isoformat()),
            )
        return token

    def consume_password_reset_token(self, token: str) -> dict | None:
        """Validate and delete a password-reset token (one-time use).

        Args:
            token: Raw token from the reset-password page.

        Returns:
            Token row dict, or ``None`` if invalid or expired.
        """
        with self.db._lock, self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM password_reset_tokens
                WHERE token_hash = ? AND expires_at > ?
                """,
                (hash_token(token), utc_now_iso()),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM password_reset_tokens WHERE id = ?", (row["id"],))
            return dict(row)

    # -------------------------------------------------------------------------
    # Notification emails — extra addresses for price alerts
    # -------------------------------------------------------------------------

    def list_notification_emails(self, user_id: int) -> list[dict]:
        """List all notification emails for a user (primary first).

        ``ORDER BY is_primary DESC`` puts the main address at the top.
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_notification_emails
                WHERE user_id = ?
                ORDER BY is_primary DESC, created_at ASC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_notification_email_by_id(self, email_id: int) -> dict | None:
        """Fetch a notification email by id (no user check — use with care)."""
        with self.db.connect() as conn:
            return row_to_dict(
                conn.execute(
                    "SELECT * FROM user_notification_emails WHERE id = ?",
                    (email_id,),
                ).fetchone()
            )

    def get_notification_email(self, email_id: int, user_id: int) -> dict | None:
        """Fetch a notification email only if it belongs to ``user_id``."""
        with self.db.connect() as conn:
            return row_to_dict(
                conn.execute(
                    "SELECT * FROM user_notification_emails WHERE id = ? AND user_id = ?",
                    (email_id, user_id),
                ).fetchone()
            )

    def get_notification_email_by_address(self, user_id: int, email: str) -> dict | None:
        """Find a notification row by address for one user (case-insensitive)."""
        with self.db.connect() as conn:
            return row_to_dict(
                conn.execute(
                    """
                    SELECT * FROM user_notification_emails
                    WHERE user_id = ? AND email = ? COLLATE NOCASE
                    """,
                    (user_id, email.strip().lower()),
                ).fetchone()
            )

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
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO user_notification_emails (user_id, email, label, verified_at, is_primary, created_at)
                VALUES (?, ?, ?, NULL, 0, ?)
                """,
                (user_id, normalized, label, now),
            )
            return dict(
                conn.execute(
                    "SELECT * FROM user_notification_emails WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
            )

    def verify_notification_email(self, email_id: int, user_id: int) -> dict | None:
        """Mark one notification address as verified.

        Returns:
            Updated row, or ``None`` if id/user mismatch.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE user_notification_emails
                SET verified_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, email_id, user_id),
            )
            return row_to_dict(
                conn.execute(
                    "SELECT * FROM user_notification_emails WHERE id = ? AND user_id = ?",
                    (email_id, user_id),
                ).fetchone()
            )

    def set_primary_notification_email(self, email_id: int, user_id: int) -> dict | None:
        """Make one verified email primary; clears ``is_primary`` on all others.

        Two UPDATEs: first zero out every row for the user, then set the chosen one.
        """
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                "UPDATE user_notification_emails SET is_primary = 0 WHERE user_id = ?",
                (user_id,),
            )
            conn.execute(
                """
                UPDATE user_notification_emails
                SET is_primary = 1
                WHERE id = ? AND user_id = ?
                """,
                (email_id, user_id),
            )
            return row_to_dict(
                conn.execute(
                    "SELECT * FROM user_notification_emails WHERE id = ? AND user_id = ?",
                    (email_id, user_id),
                ).fetchone()
            )

    def delete_notification_email(self, email_id: int, user_id: int) -> bool:
        """Delete a non-primary notification email.

        Returns:
            True if a row was deleted; False if missing or primary (protected).
        """
        with self.db._lock, self.db.connect() as conn:
            row = conn.execute(
                "SELECT is_primary FROM user_notification_emails WHERE id = ? AND user_id = ?",
                (email_id, user_id),
            ).fetchone()
            if not row or row["is_primary"]:
                return False
            cursor = conn.execute(
                "DELETE FROM user_notification_emails WHERE id = ? AND user_id = ?",
                (email_id, user_id),
            )
            return cursor.rowcount > 0

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
        with self.db._lock, self.db.connect() as conn:
            # ``ON CONFLICT DO UPDATE`` = upsert: insert or replace existing key.
            conn.execute(
                """
                INSERT INTO catalog_meta (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, json.dumps({"hash": hash_token(token), "expires": expires}), now.isoformat()),
            )
        return token

    def consume_notification_email_verification_token(
        self, email_id: int, token: str
    ) -> bool:
        """Check notification-email token and delete the meta row if valid.

        Returns:
            True if token matched and was not expired; False otherwise.
        """
        key = f"notify_email:{email_id}"
        with self.db._lock, self.db.connect() as conn:
            row = conn.execute("SELECT value FROM catalog_meta WHERE key = ?", (key,)).fetchone()
            if not row:
                return False
            payload = json.loads(row["value"])
            if payload.get("expires", "") <= utc_now_iso():
                return False
            if payload.get("hash") != hash_token(token):
                return False
            conn.execute("DELETE FROM catalog_meta WHERE key = ?", (key,))
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
        with self.db._lock, self.db.connect() as conn:
            # Housekeeping: remove expired challenges before inserting.
            conn.execute(
                "DELETE FROM webauthn_challenges WHERE expires_at <= ?",
                (utc_now_iso(),),
            )
            conn.execute(
                """
                INSERT INTO webauthn_challenges (challenge, user_id, purpose, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (challenge, user_id, purpose, expires, now.isoformat()),
            )

    def pop_webauthn_challenge(self, challenge: str, purpose: str) -> dict | None:
        """Find a challenge, delete it, and return the row (one-time use).

        "Pop" is like stack pop: read then remove so replay attacks fail.

        Returns:
            Challenge row dict, or ``None`` if missing/expired/wrong purpose.
        """
        with self.db._lock, self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM webauthn_challenges
                WHERE challenge = ? AND purpose = ? AND expires_at > ?
                """,
                (challenge, purpose, utc_now_iso()),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM webauthn_challenges WHERE id = ?", (row["id"],))
            return dict(row)

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
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO passkey_credentials (
                    user_id, credential_id, public_key, sign_count, transports,
                    friendly_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    credential_id,
                    public_key,
                    sign_count,
                    json.dumps(transports or []),
                    friendly_name,
                    now,
                ),
            )
            return dict(
                conn.execute(
                    "SELECT * FROM passkey_credentials WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
            )

    def list_passkeys(self, user_id: int) -> list[dict]:
        """List passkey metadata for account settings (no secret key material in SELECT)."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, sign_count, transports, friendly_name, created_at, last_used_at
                FROM passkey_credentials WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_passkey_by_credential_id(self, credential_id: bytes) -> dict | None:
        """Look up a passkey by the credential id from the browser's assertion."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM passkey_credentials WHERE credential_id = ?",
                (credential_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_passkey_sign_count(self, passkey_id: int, sign_count: int) -> None:
        """Update signature counter after successful login (detects cloned keys)."""
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                UPDATE passkey_credentials
                SET sign_count = ?, last_used_at = ?
                WHERE id = ?
                """,
                (sign_count, now, passkey_id),
            )

    def delete_passkey(self, passkey_id: int, user_id: int) -> bool:
        """Remove one passkey if it belongs to the user.

        Returns:
            True if a row was deleted.
        """
        with self.db._lock, self.db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM passkey_credentials WHERE id = ? AND user_id = ?",
                (passkey_id, user_id),
            )
            return cursor.rowcount > 0

    # -------------------------------------------------------------------------
    # User library — which games a logged-in user has saved
    # -------------------------------------------------------------------------

    def add_to_library(self, user_id: int, game_id: int) -> None:
        """Add a game to the user's library (no-op if already present).

        ``INSERT OR IGNORE`` skips the insert when the (user_id, game_id) pair exists.
        """
        now = utc_now_iso()
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_library (user_id, game_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, game_id, now),
            )

    def remove_from_library(self, user_id: int, game_id: int) -> bool:
        """Remove a game from library and clear any price watches for that game.

        Returns:
            True if a library row was removed.
        """
        with self.db._lock, self.db.connect() as conn:
            conn.execute(
                "DELETE FROM watches WHERE user_id = ? AND game_id = ?",
                (user_id, game_id),
            )
            cursor = conn.execute(
                "DELETE FROM user_library WHERE user_id = ? AND game_id = ?",
                (user_id, game_id),
            )
            return cursor.rowcount > 0

    def is_in_library(self, user_id: int, game_id: int) -> bool:
        """Return whether the user has saved this game."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM user_library WHERE user_id = ? AND game_id = ?",
                (user_id, game_id),
            ).fetchone()
            return row is not None

    def library_game_ids(self, user_id: int) -> set[int]:
        """Return all game ids in the user's library as a Python set."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT game_id FROM user_library WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return {row["game_id"] for row in rows}
