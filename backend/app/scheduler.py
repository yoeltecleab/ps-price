"""Background scheduler that periodically syncs the PlayStation catalog.

**What is a scheduler?**

Some work should happen *automatically on a timer* — here, refreshing the
local copy of PS Store deals.  ``PriceScheduler`` runs in the background
while the web server handles user requests.

**Async scheduling building blocks**

- ``asyncio.create_task(...)`` — starts a coroutine in the background
  without blocking ``start()``.
- ``asyncio.Event`` — a flag other code can set (``_stop.set()``) to
  signal "shut down gracefully".
- ``asyncio.wait_for(event.wait(), timeout=N)`` — sleep *up to* N seconds,
  but wake early if ``_stop`` is set (clean shutdown).

**The loop**

::

    while not stopped:
        try: sync_deals()        # pull latest catalog from PS Store
        except: log error        # one failure should not kill the scheduler
        wait feed_sync_interval  # e.g. every 60+ minutes
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from backend.app.config import Settings
from backend.app.service import PriceService


logger = logging.getLogger(__name__)


class PriceScheduler:
    """Asyncio scheduler for catalog sync and due-game refresh.

    Lifecycle:

    1. App startup calls ``await scheduler.start()``.
    2. ``_run()`` loops until ``stop()`` sets ``_stop``.
    3. App shutdown calls ``await scheduler.stop()`` which cancels the task.

    ``running`` is a read-only property other modules use to avoid starting
    duplicate background tasks.
    """

    def __init__(self, settings: Settings, service: PriceService):
        self.settings = settings
        self.service = service
        self._stop = asyncio.Event()  # cleared = keep running; set = stop
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Spawn the background task if enabled and not already running."""
        if not self.settings.scheduler_enabled or self.running:
            return
        # ``name=`` shows up in debug logs / asyncio task listings.
        self._task = asyncio.create_task(self._run(), name="ps-price-scheduler")

    async def stop(self) -> None:
        """Signal shutdown and wait for the background task to finish."""
        self._stop.set()
        if self._task:
            self._task.cancel()
            # CancelledError is expected when a task is cancelled — suppress it.
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        """Main scheduler loop — sync, then sleep, repeat."""
        while not self._stop.is_set():
            try:
                # ``sync_deals`` hits GraphQL + database — may take minutes.
                await self.service.sync_deals()
            except Exception:
                logger.exception("Scheduled catalog sync failed")
            # Enforce a minimum 60s wait even if config says something smaller.
            wait_seconds = max(60, self.settings.feed_sync_interval_minutes * 60)
            try:
                # Sleep until timeout OR until stop() sets _stop (whichever first).
                await asyncio.wait_for(self._stop.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                # Normal path: timer elapsed, run sync again.
                continue
