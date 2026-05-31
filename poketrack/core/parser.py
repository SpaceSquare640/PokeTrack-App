"""Event source parsers.

**Primary source — ``LeekDuckSource``** reads the *ScrapedDuck* dataset, a
community-maintained JSON mirror of Leek Duck's events page
(https://github.com/bigfoott/ScrapedDuck).  Consuming the structured JSON feed
is far more robust than scraping Leek Duck's HTML: a layout change on the site
won't break PokéTrack.

**Secondary source — ``PokemonGoBlogSource``** is a best-effort HTML parser for
the official Pokémon GO news page, included to show how an additional source
plugs into the same :class:`EventSource` interface.  Because it scrapes HTML, it
is more fragile and returns lightweight events (titles + links, no precise
times).

Both sources normalise their output into :class:`Event` objects and raise
typed errors (:class:`FetchError` / :class:`ParseError`) the service layer can
translate into friendly, localized messages.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import requests

from .http import DEFAULT_TIMEOUT, SESSION
from .models import Event

logger = logging.getLogger(__name__)

# Full structured feed mirroring Leek Duck's events page.
LEEKDUCK_JSON_URL = "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.json"
REQUEST_TIMEOUT = DEFAULT_TIMEOUT  # seconds


class FetchError(Exception):
    """The remote source could not be reached (network/timeout/HTTP error)."""


class ParseError(Exception):
    """The response was reached but could not be understood (format changed)."""


@runtime_checkable
class EventSource(Protocol):
    """Anything that can produce a list of events."""

    name: str

    def fetch(self) -> list[Event]:
        ...


class LeekDuckSource:
    """Primary source: ScrapedDuck JSON (a Leek Duck mirror)."""

    name = "leekduck"

    def __init__(self, url: str = LEEKDUCK_JSON_URL, timeout: int = REQUEST_TIMEOUT) -> None:
        self.url = url
        self.timeout = timeout

    def fetch(self) -> list[Event]:
        try:
            resp = SESSION.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.Timeout as exc:
            raise FetchError(f"Timed out reaching {self.url}") from exc
        except requests.RequestException as exc:
            raise FetchError(str(exc)) from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise ParseError("Response was not valid JSON") from exc

        if not isinstance(data, list):
            raise ParseError("Unexpected JSON structure (expected a list of events)")

        events: list[Event] = []
        for item in data:
            # One malformed record shouldn't sink the whole batch.
            try:
                if isinstance(item, dict):
                    events.append(Event.from_scrapedduck(item))
            except Exception as exc:  # noqa: BLE001 - defensive per-record guard
                logger.warning("Skipping malformed event record: %s", exc)

        if not events:
            raise ParseError("No events could be parsed from the source")
        logger.info("Fetched %d events from '%s'", len(events), self.name)
        return events


class PokemonGoBlogSource:
    """Secondary/best-effort source: the official Pokémon GO news page.

    The blog is HTML and its markup can change without notice, so this source is
    deliberately defensive and returns lightweight events (title + link only).
    Prefer :class:`LeekDuckSource` for full event data.
    """

    name = "blog"
    URL = "https://pokemongo.com/en/news"

    def __init__(self, url: str | None = None, timeout: int = REQUEST_TIMEOUT) -> None:
        self.url = url or self.URL
        self.timeout = timeout

    def fetch(self) -> list[Event]:
        try:
            from bs4 import BeautifulSoup  # imported lazily so it's optional
        except ImportError as exc:
            raise ParseError("beautifulsoup4 is required for the blog source") from exc

        try:
            resp = SESSION.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.Timeout as exc:
            raise FetchError(f"Timed out reaching {self.url}") from exc
        except requests.RequestException as exc:
            raise FetchError(str(exc)) from exc

        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[Event] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            title = anchor.get_text(strip=True)
            if "/news/" not in href or not title or href in seen:
                continue
            seen.add(href)
            link = href if href.startswith("http") else f"https://pokemongo.com{href}"
            events.append(
                Event(
                    event_id=link,
                    name=title,
                    event_type="news",
                    heading="News",
                    link=link,
                )
            )

        if not events:
            raise ParseError("No articles found on the blog page (markup may have changed)")
        logger.info("Fetched %d items from the blog", len(events))
        return events


# Registry so config can select a source by name.
_SOURCES: dict[str, type] = {
    LeekDuckSource.name: LeekDuckSource,
    PokemonGoBlogSource.name: PokemonGoBlogSource,
}


def get_source(name: str) -> EventSource:
    """Return a source instance by name, defaulting to Leek Duck."""
    factory = _SOURCES.get(name, LeekDuckSource)
    return factory()
