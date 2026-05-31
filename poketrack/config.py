"""User configuration management.

Loads and persists settings from ``config.json``.  Anything missing from the
file is filled from :data:`DEFAULT_CONFIG`, so the app always starts in a valid
state — even on first run, when the file is written from the defaults.

Thread-safe: the config object is shared between the GUI thread and the
APScheduler background thread.
"""
from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Canonical defaults. Missing keys in config.json are merged in from here.
DEFAULT_CONFIG: dict[str, Any] = {
    "language": "en",
    "regions": ["Global"],
    "source": "leekduck",
    "refresh_interval_minutes": 60,
    "theme": "midnight_blue",
    "database_path": "data/poketrack.db",
    "notifications": True,       # desktop/in-app alerts for new events
    "webhook_url": "",           # optional: POST new-event alerts here (Discord/Slack/custom)
    "prune_after_days": 45,      # drop events that ended more than N days ago
    "web": {
        "host": "127.0.0.1",
        "port": 5000,
        "debug": False,
    },
}


class Config:
    """A thin, thread-safe wrapper around ``config.json``."""

    def __init__(self, path: str | Path = "config.json") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """Read config from disk, merging over defaults. Never raises."""
        with self._lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    self._data = _deep_merge(copy.deepcopy(DEFAULT_CONFIG), raw)
                    logger.debug("Loaded config from %s", self.path)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Could not read %s (%s); using defaults", self.path, exc)
                    self._data = copy.deepcopy(DEFAULT_CONFIG)
            else:
                logger.info("No config file found; writing defaults to %s", self.path)
                self.save()

    def save(self) -> None:
        """Persist config to disk. Logs (does not raise) on failure."""
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(
                    json.dumps(self._data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except OSError as exc:
                logger.error("Failed to save config: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value. Supports dotted paths, e.g. ``get("web.port")``."""
        with self._lock:
            node: Any = self._data
            for part in key.split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    return default
            return copy.deepcopy(node)

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        """Write a value (dotted paths supported) and persist by default."""
        with self._lock:
            node = self._data
            parts = key.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
            if save:
                self.save()

    @property
    def data(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into ``base`` (mutates and returns base)."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
