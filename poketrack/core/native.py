"""Optional Rust fast path (loaded if the compiled extension is installed).

PokéTrack ships a small Rust/PyO3 extension (``poketrack-native/``) that parses
the ScrapedDuck feed and classifies regions in native code. It is **entirely
optional**: if the compiled ``poketrack_native`` module isn't importable, this
shim reports ``AVAILABLE = False`` and callers fall back to the pure-Python
implementations. The app behaves identically either way — native is only faster.

This mirrors the app's other optional dependencies (Pillow, plyer, pystray):
one guarded import, graceful degradation, no hard requirement.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import poketrack_native as _ext  # compiled Rust extension (abi3 wheel)

    AVAILABLE = True
    VERSION: str | None = getattr(_ext, "__version__", None)
    logger.info("Native fast path enabled (poketrack_native %s)", VERSION)
except Exception:  # noqa: BLE001 - any import problem => pure-Python fallback
    _ext = None
    AVAILABLE = False
    VERSION = None
    logger.debug("poketrack_native not available; using pure-Python data path")


def parse_feed(json_str: str, keywords: list[tuple[str, str]]) -> list[dict]:
    """Parse the raw feed JSON into event dicts. Requires :data:`AVAILABLE`."""
    return _ext.parse_feed(json_str, keywords)


def classify_region(name: str, heading: str, keywords: list[tuple[str, str]]) -> str:
    """Infer a region from name/heading. Requires :data:`AVAILABLE`."""
    return _ext.classify_region(name, heading, keywords)
