"""Best-effort desktop notifications.

Isolated here so the dependency is optional and fully guarded: if ``plyer`` is
not installed (or the platform backend fails), notifications are simply skipped
and the app carries on. The in-app "new events" indicator is the reliable path;
this is a nice-to-have on top.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify(title: str, message: str) -> bool:
    """Show an OS notification. Returns True on success, False if unavailable."""
    try:
        from plyer import notification  # imported lazily; optional dependency
    except Exception:  # noqa: BLE001 - any import problem => skip gracefully
        logger.debug("plyer unavailable; skipping desktop notification")
        return False
    try:
        notification.notify(title=title, message=message, app_name="PokéTrack", timeout=8)
        return True
    except Exception as exc:  # noqa: BLE001 - backend errors must not crash the app
        logger.debug("Desktop notification failed: %s", exc)
        return False
