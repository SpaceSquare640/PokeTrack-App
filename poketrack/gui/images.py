"""Asynchronous thumbnail loader for the desktop UI.

Remote event images must never be downloaded on the Tk main thread (that would
freeze the window). This loader fetches + decodes images on a small thread pool
and hands the finished **PIL image** back via a callback. The app then creates
the ``CTkImage`` on the main thread (Tk objects must be created there) and swaps
it into the card.

Everything degrades gracefully: if Pillow isn't installed, or a download/decode
fails, the loader simply does nothing and the card stays text-only.
"""
from __future__ import annotations

import hashlib
import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from ..core.http import SESSION

logger = logging.getLogger(__name__)

try:
    from PIL import Image  # type: ignore
    _PIL_OK = True
except Exception:  # noqa: BLE001 - Pillow is optional
    Image = None  # type: ignore
    _PIL_OK = False


class ImageLoader:
    """Downloads/decodes images off-thread with an on-disk + in-flight cache."""

    def __init__(
        self,
        cache_dir: str | Path,
        on_ready: Callable[[str, "Image.Image"], None],
        size: tuple[int, int] = (104, 104),
        workers: int = 6,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.size = size
        self._on_ready = on_ready
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="img")
        self._inflight: set[str] = set()
        self._lock = threading.Lock()
        self.enabled = _PIL_OK

    def request(self, url: str) -> None:
        """Queue an image for loading (no-op if disabled, empty, or in-flight)."""
        if not self.enabled or not url:
            return
        with self._lock:
            if url in self._inflight:
                return
            self._inflight.add(url)
        self._executor.submit(self._worker, url)

    def _worker(self, url: str) -> None:
        try:
            data = self._load_bytes(url)
            image = Image.open(io.BytesIO(data)).convert("RGBA")
            image.thumbnail(self.size)
            self._on_ready(url, image)  # delivered on this worker thread
        except Exception as exc:  # noqa: BLE001 - one bad image must not matter
            logger.debug("Image load failed for %s: %s", url, exc)
        finally:
            with self._lock:
                self._inflight.discard(url)

    def _load_bytes(self, url: str) -> bytes:
        """Return image bytes, using a small on-disk cache keyed by URL hash."""
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        path = self.cache_dir / key
        if path.exists():
            try:
                return path.read_bytes()
            except OSError:
                pass
        resp = SESSION.get(url, timeout=10)
        resp.raise_for_status()
        content = resp.content
        try:
            path.write_bytes(content)
        except OSError:
            pass
        return content

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
