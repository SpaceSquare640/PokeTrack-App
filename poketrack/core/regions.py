"""Region constants and a lightweight region classifier.

Most Pokémon GO events are global, but some — Safari Zones, GO Tour stops, City
Safaris, regional rollouts — are tied to a specific place.  The Leek Duck /
ScrapedDuck data does not tag events by region, so we *infer* a region from the
event name/heading using a curated keyword map.  Events with no strong signal
stay :data:`GLOBAL` and are shown to everyone.

The classifier is deliberately simple and easy to extend: add a
``(keyword, region)`` pair to :data:`_KEYWORDS` as the game introduces new
regional events.  Specific cities/countries are listed before broad continent
names so "Safari Zone: Taipei" resolves to Asia rather than staying Global.
"""
from __future__ import annotations

# Canonical region identifiers. Their *display* names are translated via
# languages.json ("regions" section), so these strings are stable IDs, not UI
# text — don't translate them here.
GLOBAL = "Global"
REGIONS: list[str] = [
    GLOBAL,
    "North America",
    "South America",
    "Europe",
    "Asia",
    "Oceania",
    "Africa",
]

# Ordered (keyword, region) pairs. Matching is case-insensitive substring.
# City/country signals come first; continent fallbacks come last.
_KEYWORDS: list[tuple[str, str]] = [
    # --- North America ---
    ("new york", "North America"), ("los angeles", "North America"),
    ("san diego", "North America"), ("las vegas", "North America"),
    ("chicago", "North America"), ("toronto", "North America"),
    ("vancouver", "North America"), ("mexico", "North America"),
    ("united states", "North America"), ("canada", "North America"),
    # --- South America ---
    ("são paulo", "South America"), ("sao paulo", "South America"),
    ("buenos aires", "South America"), ("santiago", "South America"),
    ("bogota", "South America"), ("lima", "South America"),
    ("brazil", "South America"), ("argentina", "South America"),
    ("chile", "South America"), ("colombia", "South America"),
    ("latin america", "South America"),
    # --- Europe ---
    ("london", "Europe"), ("paris", "Europe"), ("madrid", "Europe"),
    ("barcelona", "Europe"), ("seville", "Europe"), ("berlin", "Europe"),
    ("dortmund", "Europe"), ("amsterdam", "Europe"), ("lisbon", "Europe"),
    ("rome", "Europe"), ("milan", "Europe"), ("germany", "Europe"),
    ("france", "Europe"), ("spain", "Europe"), ("italy", "Europe"),
    ("united kingdom", "Europe"),
    # --- Asia ---
    ("taipei", "Asia"), ("taiwan", "Asia"), ("tokyo", "Asia"),
    ("osaka", "Asia"), ("yokohama", "Asia"), ("japan", "Asia"),
    ("seoul", "Asia"), ("korea", "Asia"), ("singapore", "Asia"),
    ("hong kong", "Asia"), ("bangkok", "Asia"), ("manila", "Asia"),
    ("philippines", "Asia"), ("india", "Asia"),
    # --- Oceania ---
    ("sydney", "Oceania"), ("melbourne", "Oceania"), ("perth", "Oceania"),
    ("auckland", "Oceania"), ("new zealand", "Oceania"), ("australia", "Oceania"),
    # --- Africa ---
    ("johannesburg", "Africa"), ("cape town", "Africa"), ("cairo", "Africa"),
    ("lagos", "Africa"), ("south africa", "Africa"), ("egypt", "Africa"),
    ("nigeria", "Africa"),
    # --- Continent fallbacks (checked last) ---
    ("north america", "North America"),
    ("south america", "South America"),
    ("europe", "Europe"),
    ("oceania", "Oceania"),
    ("africa", "Africa"),
    ("asia", "Asia"),
]


def classify(*texts: str) -> str:
    """Infer a region from one or more text fields (name, heading, …).

    Returns the first matching region, or :data:`GLOBAL` when nothing matches.
    """
    haystack = " ".join(t for t in texts if t).lower()
    for keyword, region in _KEYWORDS:
        if keyword in haystack:
            return region
    return GLOBAL
