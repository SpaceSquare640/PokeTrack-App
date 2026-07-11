"""Optional GitHub release update check.

Asks the GitHub API for the latest release tag and compares it to the running
version. Entirely best-effort: any network/parse error (or hitting the
unauthenticated rate limit) just returns ``None`` — the app never blocks or
errors on this. Reuses the shared retrying HTTP session.
"""
from __future__ import annotations

import logging
from typing import Optional

from .http import DEFAULT_TIMEOUT, SESSION

logger = logging.getLogger(__name__)

OWNER_REPO = "SpaceSquare640/PokeTrack-App"
LATEST_API = f"https://api.github.com/repos/{OWNER_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{OWNER_REPO}/releases"


def _parse_version(text: str) -> tuple[int, ...]:
    """Parse ``"v1.5.1"`` / ``"1.5.1"`` into ``(1, 5, 1)``; empty tuple if unparseable."""
    text = text.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in text.split("."):
        num = "".join(c for c in chunk if c.isdigit())
        if not num:
            break
        parts.append(int(num))
    return tuple(parts)


def check(current_version: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[dict]:
    """Return ``{"version": "1.5.2", "url": ...}`` if a newer release exists, else None."""
    current = _parse_version(current_version)
    if not current:
        return None
    try:
        resp = SESSION.get(LATEST_API, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 - update check is best-effort only
        logger.debug("Update check failed", exc_info=True)
        return None
    tag = str(data.get("tag_name", ""))
    latest = _parse_version(tag)
    if latest and latest > current:
        return {"version": tag.lstrip("vV"), "url": data.get("html_url") or RELEASES_PAGE}
    return None
