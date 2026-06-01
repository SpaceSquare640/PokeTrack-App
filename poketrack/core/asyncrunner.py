"""A shared background asyncio event loop.

Tkinter and Flask aren't async-native, so PokéTrack hosts a single asyncio loop
on a daemon thread. This lets the codebase use ``async/await`` for network work
without blocking the GUI main thread:

* The desktop GUI calls :meth:`AsyncRunner.submit` and gets a ``Future`` back —
  it never blocks the Tk main loop; the result is delivered via the UI queue.
* Sync callers (Flask request handlers, the scheduler, tests) can call
  :meth:`AsyncRunner.run` to await a coroutine to completion *on a worker
  thread* (never the GUI thread).

The loop starts lazily on first use, so importing this module is cheap and tests
that never touch the network never spin it up.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


class AsyncRunner:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure_running(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop, name="poketrack-async", daemon=True
            )
            self._thread.start()
            logger.debug("Async event loop started")
            return self._loop

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro: Coroutine) -> Future:
        """Schedule a coroutine on the background loop; returns a Future.

        Safe to call from any thread *except* the loop thread itself.
        """
        loop = self._ensure_running()
        return asyncio.run_coroutine_threadsafe(coro, loop)

    def run(self, coro: Coroutine) -> Any:
        """Run a coroutine to completion and return its result (blocking)."""
        return self.submit(coro).result()

    def shutdown(self) -> None:
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
                logger.debug("Async event loop stopping")


# Process-wide singleton.
RUNNER = AsyncRunner()
