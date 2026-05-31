"""The :class:`Event` domain model.

A single, source-agnostic representation of a Pokémon GO event.  Parsers convert
raw source records into ``Event`` objects; the database stores/loads them; both
UIs render them.  Keeping the model in one place means the rest of the app never
has to care which website the data came from.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .regions import GLOBAL, classify

logger = logging.getLogger(__name__)


def _highlights_from_extra(extra: Any) -> dict[str, Any]:
    """Pull display-worthy bits out of the source's ``extraData`` blob.

    The feed has no prose description, but it does carry structured extras
    (raid bosses, promo codes, spawn/research flags). We distil those into a
    small, stable dict the description builder can localise later.
    """
    out: dict[str, Any] = {"bosses": [], "promocodes": [], "has_spawns": False, "has_research": False}
    if not isinstance(extra, dict):
        return out
    raid = extra.get("raidbattles") or {}
    if isinstance(raid, dict):
        out["bosses"] = [b.get("name") for b in raid.get("bosses", []) if isinstance(b, dict) and b.get("name")]
    promos = extra.get("promocodes")
    if isinstance(promos, list):
        out["promocodes"] = [p for p in promos if isinstance(p, str)]
    generic = extra.get("generic") or {}
    if isinstance(generic, dict):
        out["has_spawns"] = bool(generic.get("hasSpawns"))
        out["has_research"] = bool(generic.get("hasFieldResearchTasks"))
    return out


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse the various ISO-ish datetime strings sources emit. Never raises.

    Returns a **timezone-naive** datetime in local wall-clock time. Most source
    values are already naive local (e.g. ``"2024-05-19T14:00:00.000"``), but some
    carry an offset (``...Z`` / ``...+09:00``); those are converted to local time
    and stripped of tzinfo. Normalising to naive here means every downstream
    comparison (e.g. in :meth:`Event.status`) is consistent and never raises
    "can't compare offset-naive and offset-aware datetimes".
    """
    if not value:
        return None
    text = value.strip()
    parsed: Optional[datetime] = None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            logger.debug("Unparseable datetime: %r", value)
            return None
    # Collapse any timezone-aware value to naive local wall-clock time.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


@dataclass
class Event:
    """One community event/activity."""

    event_id: str
    name: str
    event_type: str = ""
    heading: str = ""
    link: str = ""
    image: str = ""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    region: str = GLOBAL
    # Structured highlights distilled from the source's extraData.
    bosses: list[str] = field(default_factory=list)
    promocodes: list[str] = field(default_factory=list)
    has_spawns: bool = False
    has_research: bool = False

    # ------------------------------------------------------------------ #
    # Construction from sources                                          #
    # ------------------------------------------------------------------ #
    @classmethod
    def from_scrapedduck(cls, item: dict[str, Any]) -> "Event":
        """Build an Event from one ScrapedDuck/Leek Duck JSON record."""
        name = item.get("name") or item.get("heading") or "Untitled event"
        heading = item.get("heading", "") or ""
        hl = _highlights_from_extra(item.get("extraData"))
        return cls(
            event_id=str(item.get("eventID") or item.get("link") or name),
            name=name,
            event_type=item.get("eventType", "") or "",
            heading=heading,
            link=item.get("link", "") or "",
            image=item.get("image", "") or "",
            start=_parse_dt(item.get("start")),
            end=_parse_dt(item.get("end")),
            region=classify(name, heading),
            bosses=hl["bosses"],
            promocodes=hl["promocodes"],
            has_spawns=hl["has_spawns"],
            has_research=hl["has_research"],
        )

    # ------------------------------------------------------------------ #
    # Status logic                                                       #
    # ------------------------------------------------------------------ #
    def status(self, now: Optional[datetime] = None) -> str:
        """One of ``active`` / ``upcoming`` / ``ended`` / ``unknown``."""
        now = now or datetime.now()
        if self.start and now < self.start:
            return "upcoming"
        if self.end and now > self.end:
            return "ended"
        if self.start and self.start <= now and (self.end is None or now <= self.end):
            return "active"
        return "unknown"

    def is_active(self, now: Optional[datetime] = None) -> bool:
        return self.status(now) == "active"

    def is_upcoming(self, now: Optional[datetime] = None) -> bool:
        return self.status(now) == "upcoming"

    @property
    def type_label(self) -> str:
        """Human-friendly event type, e.g. ``community-day`` -> ``Community Day``."""
        return self.event_type.replace("-", " ").title() if self.event_type else ""

    # ------------------------------------------------------------------ #
    # Serialisation                                                      #
    # ------------------------------------------------------------------ #
    def to_row(self) -> dict[str, Any]:
        """Column dict for SQLite (datetimes -> ISO strings, highlights -> JSON)."""
        return {
            "event_id": self.event_id,
            "name": self.name,
            "event_type": self.event_type,
            "heading": self.heading,
            "link": self.link,
            "image": self.image,
            "start_time": self.start.isoformat() if self.start else None,
            "end_time": self.end.isoformat() if self.end else None,
            "region": self.region,
            "extra": json.dumps({
                "bosses": self.bosses,
                "promocodes": self.promocodes,
                "has_spawns": self.has_spawns,
                "has_research": self.has_research,
            }, ensure_ascii=False),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Event":
        """Rebuild an Event from a SQLite row dict."""
        extra: dict[str, Any] = {}
        raw_extra = row.get("extra") if hasattr(row, "get") else None
        if raw_extra:
            try:
                extra = json.loads(raw_extra)
            except (ValueError, TypeError):
                extra = {}
        return cls(
            event_id=row["event_id"],
            name=row["name"],
            event_type=row["event_type"] or "",
            heading=row["heading"] or "",
            link=row["link"] or "",
            image=row["image"] or "",
            start=_parse_dt(row["start_time"]),
            end=_parse_dt(row["end_time"]),
            region=row["region"] or GLOBAL,
            bosses=extra.get("bosses", []) or [],
            promocodes=extra.get("promocodes", []) or [],
            has_spawns=bool(extra.get("has_spawns")),
            has_research=bool(extra.get("has_research")),
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict for the web layer / API (incl. display strings)."""
        return {
            "event_id": self.event_id,
            "name": self.name,
            "event_type": self.event_type,
            "type_label": self.type_label,
            "heading": self.heading,
            "link": self.link,
            "image": self.image,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "start_display": self.format_time(self.start),
            "end_display": self.format_time(self.end),
            "region": self.region,
            "status": self.status(),
        }

    @staticmethod
    def format_time(value: Optional[datetime]) -> str:
        """Human-readable local time, or an em dash when unknown."""
        if not value:
            return "—"
        return value.strftime("%b %d, %Y · %H:%M")
