"""Background scheduler that periodically syncs the PlayStation catalog."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from backend.app.config import Settings
from backend.app.service import PriceService


logger = logging.getLogger(__name__)


class PriceScheduler:
    """Asyncio scheduler for catalog sync and due-game refresh."""

    def __init__(self, settings: Settings, service: PriceService):
        self.settings = settings
        self.service = service
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if not self.settings.scheduler_enabled or self.running:
            return
        self._task = asyncio.create_task(self._run(), name="ps-price-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.service.sync_deals()
            except Exception:
                logger.exception("Scheduled catalog sync failed")
            wait_seconds = max(60, self.settings.feed_sync_interval_minutes * 60)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                continue
