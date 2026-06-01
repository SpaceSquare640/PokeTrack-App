"""Region constants and a lightweight, data-driven region classifier.

Most Pokémon GO events are global, but some — Safari Zones, GO Tour stops, City
Safaris, regional rollouts — are tied to a specific place.  The Leek Duck /
ScrapedDuck data does not tag events by region, so we *infer* a region from the
event name/heading using a keyword map.  Events with no strong signal stay
:data:`GLOBAL` and are shown to everyone.

The rules live in **``data/regions_map.json``** (project root), so users can add
cities/countries without touching Python.  This module loads that file at import
time and falls back to a built-in default if the file is missing or malformed,
so the classifier always works.  Call :func:`reload` to re-read the file at
runtime (e.g. after the user edits it).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

GLOBAL = "Global"

# Project root → data/regions_map.json (regions.py is poketrack/core/regions.py).
_MAP_PATH = Path(__file__).resolve().parents[2] / "data" / "regions_map.json"

# Built-in fallback, used only if the JSON file can't be read. Kept minimal but
# functional so region tagging never breaks.
_DEFAULT_REGIONS: list[str] = [
    GLOBAL, "North America", "South America", "Europe", "Asia", "Oceania", "Africa",
]
_DEFAULT_KEYWORDS: list[tuple[str, str]] = [
    ("new york", "North America"), ("los angeles", "North America"),
    ("united states", "North America"), ("canada", "North America"),
    ("são paulo", "South America"), ("sao paulo", "South America"),
    ("brazil", "South America"), ("latin america", "South America"),
    ("london", "Europe"), ("paris", "Europe"), ("berlin", "Europe"),
    ("taipei", "Asia"), ("tokyo", "Asia"), ("japan", "Asia"), ("korea", "Asia"),
    ("sydney", "Oceania"), ("australia", "Oceania"), ("new zealand", "Oceania"),
    ("johannesburg", "Africa"), ("south africa", "Africa"),
    ("north america", "North America"), ("south america", "South America"),
    ("europe", "Europe"), ("oceania", "Oceania"), ("africa", "Africa"), ("asia", "Asia"),
]

# Populated by _load() at import (and by reload()).
REGIONS: list[str] = []
_KEYWORDS: list[tuple[str, str]] = []


def _load() -> None:
    """(Re)load REGIONS and _KEYWORDS from the JSON map, with safe fallback."""
    global REGIONS, _KEYWORDS
    try:
        raw = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
        regions = raw.get("regions")
        keywords = raw.get("keywords")
        if not isinstance(regions, list) or not isinstance(keywords, list):
            raise ValueError("regions_map.json missing 'regions'/'keywords' lists")
        # Normalise keyword pairs to (lowercase keyword, region) tuples.
        pairs: list[tuple[str, str]] = []
        for item in keywords:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                pairs.append((str(item[0]).lower(), str(item[1])))
        REGIONS = [str(r) for r in regions] or list(_DEFAULT_REGIONS)
        _KEYWORDS = pairs or list(_DEFAULT_KEYWORDS)
        logger.debug("Loaded %d region keywords from %s", len(_KEYWORDS), _MAP_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Could not load %s (%s); using built-in region defaults", _MAP_PATH, exc)
        REGIONS = list(_DEFAULT_REGIONS)
        _KEYWORDS = list(_DEFAULT_KEYWORDS)


def reload() -> None:
    """Public hook to re-read the region map after the user edits it."""
    _load()


def classify(*texts: str) -> str:
    """Infer a region from one or more text fields (name, heading, …).

    Returns the first matching region, or :data:`GLOBAL` when nothing matches.
    """
    haystack = " ".join(t for t in texts if t).lower()
    for keyword, region in _KEYWORDS:
        if keyword in haystack:
            return region
    return GLOBAL


# Load once at import.
_load()
