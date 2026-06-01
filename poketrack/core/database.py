"""SQLite persistence for fetched events.

Design notes
------------
* **One connection per operation.** SQLite connections aren't meant to be shared
  across threads; opening a short-lived connection per call lets the GUI thread
  and the APScheduler background thread use the same database safely.
* **WAL journal mode** keeps concurrent reads/writes smooth.
* **Upsert** on ``event_id`` so re-fetching simply refreshes existing rows
  instead of duplicating them.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from .models import Event
from .regions import GLOBAL

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    event_type  TEXT,
    heading     TEXT,
    link        TEXT,
    image       TEXT,
    start_time  TEXT,
    end_time    TEXT,
    region      TEXT DEFAULT 'Global',
    extra       TEXT,
    fetched_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_region ON events(region);
CREATE INDEX IF NOT EXISTS idx_events_start  ON events(start_time);
CREATE INDEX IF NOT EXISTS idx_events_name   ON events(name);
"""

# Columns added after the initial release, applied as lightweight migrations so
# existing databases upgrade in place without losing data.
_MIGRATIONS = {
    "extra": "ALTER TABLE events ADD COLUMN extra TEXT",
}


class Database:
    """Thread-safe SQLite store for :class:`Event` objects."""

    def __init__(self, path: str | Path = "data/poketrack.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            # Apply column migrations for databases created by older versions.
            existing = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
            for column, ddl in _MIGRATIONS.items():
                if column not in existing:
                    conn.execute(ddl)
                    logger.info("Migrated database: added column '%s'", column)
            conn.commit()

    # ------------------------------------------------------------------ #
    # Writes                                                             #
    # ------------------------------------------------------------------ #
    def upsert_events(self, events: Iterable[Event]) -> int:
        """Insert new events / refresh existing ones. Returns rows written."""
        events = list(events)
        if not events:
            return 0
        now = datetime.now().isoformat()
        sql = """
        INSERT INTO events (event_id, name, event_type, heading, link, image,
                            start_time, end_time, region, extra, fetched_at)
        VALUES (:event_id, :name, :event_type, :heading, :link, :image,
                :start_time, :end_time, :region, :extra, :fetched_at)
        ON CONFLICT(event_id) DO UPDATE SET
            name       = excluded.name,
            event_type = excluded.event_type,
            heading    = excluded.heading,
            link       = excluded.link,
            image      = excluded.image,
            start_time = excluded.start_time,
            end_time   = excluded.end_time,
            region     = excluded.region,
            extra      = excluded.extra,
            fetched_at = excluded.fetched_at;
        """
        rows = []
        for event in events:
            row = event.to_row()
            row["fetched_at"] = now
            rows.append(row)
        with closing(self._connect()) as conn:
            conn.executemany(sql, rows)
            conn.commit()
        logger.info("Upserted %d events", len(rows))
        return len(rows)

    def clear(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM events")
            conn.commit()

    # ------------------------------------------------------------------ #
    # Reads                                                              #
    # ------------------------------------------------------------------ #
    def get_events(
        self,
        *,
        regions: Optional[Iterable[str]] = None,
        statuses: Optional[Iterable[str]] = None,
        event_types: Optional[Iterable[str]] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Event]:
        """Query events.

        ``regions`` filters by region but always includes Global events (they're
        relevant everywhere).  ``event_types`` filters by raw event type.
        ``statuses`` filters by computed status in Python (since status depends
        on the current time, not on stored data).
        """
        clauses: list[str] = []
        params: list = []

        if regions:
            wanted = set(regions)
            wanted.add(GLOBAL)  # Global events are always relevant
            placeholders = ",".join("?" for _ in wanted)
            clauses.append(f"region IN ({placeholders})")
            params.extend(sorted(wanted))

        if event_types:
            types = list(event_types)
            placeholders = ",".join("?" for _ in types)
            clauses.append(f"event_type IN ({placeholders})")
            params.extend(types)

        if search:
            clauses.append("(LOWER(name) LIKE ? OR LOWER(heading) LIKE ?)")
            term = f"%{search.lower()}%"
            params.extend([term, term])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # NULL start times sort last; otherwise ascending by start.
        sql = f"SELECT * FROM events {where} ORDER BY start_time IS NULL, start_time ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()

        events = [Event.from_row(dict(r)) for r in rows]
        if statuses:
            wanted_status = set(statuses)
            events = [e for e in events if e.status() in wanted_status]
        return events

    def get_event(self, event_id: str) -> Optional[Event]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return Event.from_row(dict(row)) if row else None

    def count(self) -> int:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def existing_ids(self) -> set[str]:
        """All event IDs currently stored — used to detect newly-added events."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT event_id FROM events").fetchall()
        return {r[0] for r in rows}

    def distinct_types(self) -> list[str]:
        """Sorted list of non-empty event types present in the database."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT DISTINCT event_type FROM events "
                "WHERE event_type IS NOT NULL AND event_type != '' ORDER BY event_type"
            ).fetchall()
        return [r[0] for r in rows]

    def last_updated(self) -> Optional[str]:
        """ISO timestamp of the most recent fetch, or None if the db is empty."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT MAX(fetched_at) FROM events").fetchone()
        return row[0] if row and row[0] else None

    def prune_old(self, days: int) -> int:
        """Delete events that ended more than ``days`` ago. Returns rows removed.

        Keeps the local store tidy without losing anything still relevant. Events
        with no end time are never pruned.
        """
        if not days or days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "DELETE FROM events WHERE end_time IS NOT NULL AND end_time < ?", (cutoff,)
            )
            conn.commit()
            removed = cur.rowcount
        if removed:
            logger.info("Pruned %d events that ended over %d days ago", removed, days)
        return removed
