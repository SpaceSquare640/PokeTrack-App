"""iCalendar (.ics) generation for events.

Hand-rolled (no dependency) — the iCalendar text format is simple and stable.
Event times are naive local wall-clock (the source's convention), so we emit
them as **floating** times (no ``Z`` / no ``TZID``), which calendar apps display
in the viewer's local time — the right behaviour for global Pokémon GO events.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable, Optional


def _escape(text: str) -> str:
    """Escape per RFC 5545 (backslash, semicolon, comma, newline)."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fmt(dt: datetime, *, utc: bool = False) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ" if utc else "%Y%m%dT%H%M%S")


def build_ics(
    events: Iterable,
    *,
    name: str = "PokéTrack",
    describe: Optional[Callable[[object], str]] = None,
) -> str:
    """Build a VCALENDAR string from events (those without a start are skipped)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PokeTrack//Pokemon GO Events//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
    ]
    stamp = _fmt(datetime.now(timezone.utc), utc=True)
    for event in events:
        start = getattr(event, "start", None)
        if not start:
            continue
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{_escape(str(event.event_id))}@poketrack")
        lines.append(f"DTSTAMP:{stamp}")
        lines.append(f"DTSTART:{_fmt(start)}")
        if getattr(event, "end", None):
            lines.append(f"DTEND:{_fmt(event.end)}")
        lines.append(f"SUMMARY:{_escape(event.name)}")
        desc = describe(event) if describe else getattr(event, "heading", "")
        if desc:
            lines.append(f"DESCRIPTION:{_escape(desc)}")
        if getattr(event, "link", ""):
            lines.append(f"URL:{_escape(event.link)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
