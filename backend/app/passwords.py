"""Password hashing with Argon2.

Why this file exists
--------------------
We must **never** store a user's real password in the database. If the
database leaked, attackers could log in as everyone. Instead we store a
**hash** — a one-way scrambled version that can be checked but not reversed.

Argon2 is a modern algorithm designed to be slow on purpose, which makes
brute-force guessing expensive for attackers.

Flow:
  1. User registers → ``hash_password("their secret")`` → save hash in DB
  2. User logs in  → ``verify_password("their secret", stored_hash)`` → True/False

See ``auth_service.py`` for where these functions are called.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# One shared hasher instance for the whole app (creating it is slightly expensive).
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Turn a plain-text password into an Argon2 hash string for storage.

    Args:
        password: What the user typed (e.g. at registration).

    Returns:
        A long encoded string safe to save in the ``users.password_hash`` column.
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check whether ``password`` matches a previously stored hash.

    Args:
        password: What the user just typed at login.
        password_hash: Value from the database (or None if account has no password).

    Returns:
        True if the password is correct, False otherwise.
    """
    if not password_hash:
        # Passkey-only accounts may have no password hash.
        return False
    try:
        # verify() re-hashes the password and compares; raises on mismatch.
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
