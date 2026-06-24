"""In-memory sliding-window rate limiter for abuse-sensitive endpoints.

What is rate limiting?
----------------------
If someone spams ``POST /api/auth/login`` thousands of times, they might
guess passwords or overload the server. Rate limiting says: "only N requests
per key per time window" — extra requests get HTTP 429 Too Many Requests.

This implementation keeps timestamps in memory (a ``deque`` per key). It is
**thread-safe** and fine for a **single server**. If you run many backend
instances behind a load balancer, each instance has its own counter (a known
limitation documented in deployment docs).

Keys are chosen by callers, e.g. ``f"login:{email}"`` or ``f"register:{ip}"``.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Thread-safe per-key sliding window rate limiter."""

    def __init__(self) -> None:
        # RLock = re-entrant lock; same thread can acquire it multiple times.
        self._lock = threading.RLock()
        # Maps a string key → deque of monotonic timestamps for recent requests.
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Record one request for ``key`` or raise HTTP 429 if over the limit.

        Algorithm (sliding window):
          1. Drop timestamps older than ``window_seconds``.
          2. If count >= ``limit``, reject.
          3. Otherwise append "now" and allow the request.

        Args:
            key: Identifier for who/what is being limited (email, IP, user id).
            limit: Maximum allowed requests in the window.
            window_seconds: Length of the window in seconds.

        Raises:
            HTTPException: 429 when the limit is exceeded.
        """
        now = time.monotonic()  # Monotonic clock — never goes backwards.
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            # Remove expired entries from the left (oldest first).
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="too many requests — try again later",
                )
            bucket.append(now)

    def client_ip(self, request: Request) -> str:
        """Best-effort client IP for rate-limit keys behind a reverse proxy.

        Checks ``X-Forwarded-For`` first (set by Caddy/nginx), then the direct
        TCP client address.
        """
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First IP in the list is the original client.
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def active_bucket_count(self) -> int:
        with self._lock:
            return sum(1 for bucket in self._events.values() if bucket)

    def reset(self) -> None:
        """Clear all buckets. Used by tests so one test does not 429 the next."""
        with self._lock:
            self._events.clear()


# Single shared limiter for the whole application process.
rate_limiter = RateLimiter()
