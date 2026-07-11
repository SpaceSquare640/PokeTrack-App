"""Event source parsers (sync + async).

**Primary source — ``LeekDuckSource``** reads the *ScrapedDuck* dataset, a
community-maintained JSON mirror of Leek Duck's events page
(https://github.com/bigfoott/ScrapedDuck).  Consuming the structured JSON feed
is far more robust than scraping Leek Duck's HTML: a layout change on the site
won't break PokéTrack.

**Secondary source — ``PokemonGoBlogSource``** is a best-effort HTML parser for
the official Pokémon GO news page, behind the same interface.

Each source offers two entry points sharing one parse routine:

* ``fetch()``        — synchronous (``requests``); used by the web app, the
  scheduler, and tests.
* ``fetch_async()``  — ``async``/``await`` (``httpx``); used by the desktop GUI
  so network I/O never blocks the Tk main thread.

Both raise typed errors (:class:`FetchError` / :class:`ParseError`) the service
layer maps to friendly, localized messages.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol, runtime_checkable

import httpx
import requests

from . import native, regions
from .http import DEFAULT_TIMEOUT, SESSION, USER_AGENT
from .models import Event

logger = logging.getLogger(__name__)

# Full structured feed mirroring Leek Duck's events page.
LEEKDUCK_JSON_URL = "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.json"
REQUEST_TIMEOUT = DEFAULT_TIMEOUT  # seconds

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF = 0.6  # seconds: 0.6, 1.2, 2.4 …


class FetchError(Exception):
    """The remote source could not be reached (network/timeout/HTTP error)."""


class ParseError(Exception):
    """The response was reached but could not be understood (format changed)."""


@runtime_checkable
class EventSource(Protocol):
    """Anything that can produce a list of events, sync or async."""

    name: str

    def fetch(self) -> list[Event]:
        ...

    async def fetch_async(self) -> list[Event]:
        ...


async def _aget(url: str, timeout: float) -> httpx.Response:
    """Async GET with retries/backoff on transient failures. Raises FetchError."""
    last: Exception | None = None
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as client:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await client.get(url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
            else:
                if resp.status_code not in _RETRY_STATUSES:
                    return resp
                last = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF * (2 ** attempt))
    raise FetchError(f"Failed to reach {url}: {last}")


class LeekDuckSource:
    """Primary source: ScrapedDuck JSON (a Leek Duck mirror)."""

    name = "leekduck"

    def __init__(self, url: str = LEEKDUCK_JSON_URL, timeout: int = REQUEST_TIMEOUT) -> None:
        self.url = url
        self.timeout = timeout

    # --- shared parse routines (used by both sync and async fetch) ------ #
    def _parse_text(self, text: str) -> list[Event]:
        """Parse raw feed JSON text: Rust fast path if present, else pure Python.

        The native path parses + classifies in one call; any native hiccup falls
        back to the pure-Python loop, so behaviour is identical either way.
        """
        if native.AVAILABLE:
            try:
                records = native.parse_feed(text, regions.keyword_pairs())
                events = [Event.from_native(r) for r in records]
                if not events:
                    raise ParseError("No events could be parsed from the source")
                logger.info("Fetched %d events from '%s' (native)", len(events), self.name)
                return events
            except ParseError:
                raise
            except Exception as exc:  # noqa: BLE001 - native error => pure-Python fallback
                logger.warning("Native parse failed (%s); falling back to Python", exc)
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ParseError("Response was not valid JSON") from exc
        return self._parse_feed(data)

    def _parse_feed(self, data: Any) -> list[Event]:
        if not isinstance(data, list):
            raise ParseError("Unexpected JSON structure (expected a list of events)")
        events: list[Event] = []
        for item in data:
            try:
                if isinstance(item, dict):
                    events.append(Event.from_scrapedduck(item))
            except Exception as exc:  # noqa: BLE001 - one bad record can't sink the batch
                logger.warning("Skipping malformed event record: %s", exc)
        if not events:
            raise ParseError("No events could be parsed from the source")
        logger.info("Fetched %d events from '%s'", len(events), self.name)
        return events

    def fetch(self) -> list[Event]:
        try:
            resp = SESSION.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.Timeout as exc:
            raise FetchError(f"Timed out reaching {self.url}") from exc
        except requests.RequestException as exc:
            raise FetchError(str(exc)) from exc
        return self._parse_text(resp.text)

    async def fetch_async(self) -> list[Event]:
        resp = await _aget(self.url, self.timeout)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FetchError(str(exc)) from exc
        return self._parse_text(resp.text)


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

    def _parse_html(self, text: str) -> list[Event]:
        try:
            from bs4 import BeautifulSoup  # imported lazily so it's optional
        except ImportError as exc:
            raise ParseError("beautifulsoup4 is required for the blog source") from exc
        soup = BeautifulSoup(text, "html.parser")
        events: list[Event] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            title = anchor.get_text(strip=True)
            if "/news/" not in href or not title or href in seen:
                continue
            seen.add(href)
            link = href if href.startswith("http") else f"https://pokemongo.com{href}"
            events.append(Event(event_id=link, name=title, event_type="news", heading="News", link=link))
        if not events:
            raise ParseError("No articles found on the blog page (markup may have changed)")
        logger.info("Fetched %d items from the blog", len(events))
        return events

    def fetch(self) -> list[Event]:
        try:
            resp = SESSION.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.Timeout as exc:
            raise FetchError(f"Timed out reaching {self.url}") from exc
        except requests.RequestException as exc:
            raise FetchError(str(exc)) from exc
        return self._parse_html(resp.text)

    async def fetch_async(self) -> list[Event]:
        resp = await _aget(self.url, self.timeout)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FetchError(str(exc)) from exc
        return self._parse_html(resp.text)


# Registry so config can select a source by name.
_SOURCES: dict[str, type] = {
    LeekDuckSource.name: LeekDuckSource,
    PokemonGoBlogSource.name: PokemonGoBlogSource,
}


def get_source(name: str) -> EventSource:
    """Return a source instance by name, defaulting to Leek Duck."""
    factory = _SOURCES.get(name, LeekDuckSource)
    return factory()
