"""Background update scheduling via APScheduler.

A thin wrapper around APScheduler's :class:`BackgroundScheduler` that runs a
single recurring job on a minute interval.  The wrapper swallows job exceptions
so a transient failure (e.g. the network is down) can never kill the scheduler
thread — the next tick simply tries again.
"""
from __future__ import annotations

import logging
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


class UpdateScheduler:
    """Runs ``job`` every ``interval_minutes`` on a background thread."""

    JOB_ID = "poketrack_update"

    def __init__(self, job: Callable[[], None], interval_minutes: int = 60) -> None:
        self._job = job
        self._interval = max(1, int(interval_minutes))
        self._scheduler = BackgroundScheduler(daemon=True)

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self._safe_job,
            trigger="interval",
            minutes=self._interval,
            id=self.JOB_ID,
            replace_existing=True,
            max_instances=1,   # never overlap two fetches
            coalesce=True,     # collapse missed runs into one
        )
        self._scheduler.start()
        logger.info("Scheduler started (every %d min)", self._interval)

    def reschedule(self, interval_minutes: int) -> None:
        self._interval = max(1, int(interval_minutes))
        if self._scheduler.running:
            self._scheduler.reschedule_job(
                self.JOB_ID, trigger="interval", minutes=self._interval
            )
            logger.info("Scheduler interval changed to %d min", self._interval)

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def _safe_job(self) -> None:
        try:
            self._job()
        except Exception:  # noqa: BLE001 - keep the scheduler thread alive
            logger.exception("Scheduled update failed")
