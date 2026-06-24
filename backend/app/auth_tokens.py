"""Token generation and hashing for sessions and email links.

What is a "token"?
------------------
A token is a long random string (like a temporary password) sent to the user
in a link, e.g. "verify your email" or "reset your password". We also use
tokens for **session cookies** after login.

Security rules used here:
  - **Generate** with ``secrets`` (cryptographically random, hard to guess).
  - **Store** only a SHA-256 **hash** in the database, not the raw token.
    If the DB leaks, attackers still cannot forge valid session cookies.

Example lifecycle (email verification):
  1. ``token = new_token()``  → send ``token`` in email link
  2. ``hash_token(token)``    → save hash in ``email_verification_tokens`` table
  3. User clicks link; we hash their token and look up the row
"""

from __future__ import annotations

import hashlib
import secrets


def new_token() -> str:
    """Create a new unpredictable URL-safe token (43+ characters).

    Uses Python's ``secrets`` module — suitable for security-sensitive values.
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """One-way SHA-256 hash of a token for database storage.

    We never store the raw session or verification token in the database.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
