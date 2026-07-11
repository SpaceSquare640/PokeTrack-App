"""Application service layer — the single controller both UIs use.

``PokeTrackService`` wires together config, database, parser and scheduler, and
exposes a small, UI-agnostic API:

* :meth:`refresh_now`   — fetch, persist, detect new events, prune old ones.
* :meth:`get_events`    — read events, honouring region / type / search filters.
* :meth:`countdown`     — localized "starts in 3h" / "ends in 2d" strings.
* :meth:`available_types` — event types present, for the type filter UI.
* settings setters + lifecycle (:meth:`start` / :meth:`stop`).

The desktop GUI and the Flask app talk *only* to this object — never to the
parser or database directly — which keeps fetching and presentation separated.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from .. import __version__
from ..config import Config
from ..i18n import Translator
from . import calendar as ical
from . import telegram, updates, webhook
from .database import Database
from .models import Event
from .notify import notify
from .parser import FetchError, ParseError, get_source
from .regions import GLOBAL
from .scheduler import UpdateScheduler

logger = logging.getLogger(__name__)


class RefreshResult:
    """Outcome of a fetch attempt.

    On failure, ``error_key`` is an i18n key under ``errors.*``.  On success,
    ``new_events`` lists events not previously stored (empty on the very first
    populate, so the app doesn't announce 60 "new" events at once).
    """

    def __init__(
        self,
        ok: bool,
        count: int = 0,
        error_key: Optional[str] = None,
        new_events: Optional[list[Event]] = None,
        first_load: bool = False,
    ) -> None:
        self.ok = ok
        self.count = count
        self.error_key = error_key
        self.new_events: list[Event] = new_events or []
        self.first_load = first_load

    @property
    def new_count(self) -> int:
        return len(self.new_events)


class PokeTrackService:
    def __init__(self, config: Config, translator: Translator, database: Database) -> None:
        self.config = config
        self.translator = translator
        self.db = database
        self._lock = threading.Lock()
        self._scheduler = UpdateScheduler(
            job=self._scheduled_refresh,
            interval_minutes=config.get("refresh_interval_minutes", 60),
        )
        # Optional callback fired after every background refresh (used by the
        # desktop UI to re-render). Receives a RefreshResult.
        self.on_update: Optional[Callable[[RefreshResult], None]] = None
        # Event IDs already reminded about, so a "starting soon" alert fires once.
        self._reminded: set[str] = set()
        # Cached result of the GitHub update check (None = up to date / not checked).
        self._update_available: Optional[dict] = None
        # Optional callback fired when a newer release is detected (for the desktop UI).
        self.on_update_available: Optional[Callable[[dict], None]] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #
    def start(self, refresh_now: bool = True) -> None:
        """Start the background scheduler and (optionally) fetch immediately."""
        self._scheduler.start()
        # Reminder check runs every minute (independent of the fetch interval, so a
        # long refresh interval doesn't miss the "starts in X min" window).
        self._scheduler.add_interval_job(self._check_reminders, minutes=1, job_id="poketrack_reminders")
        # Update check: once at startup (off-thread) + every 6 hours.
        self._scheduler.add_interval_job(self._check_update, minutes=360, job_id="poketrack_update_check")
        threading.Thread(target=self._check_update, daemon=True).start()
        if refresh_now:
            threading.Thread(target=self._scheduled_refresh, daemon=True).start()

    def stop(self) -> None:
        self._scheduler.stop()

    # ------------------------------------------------------------------ #
    # Fetching                                                           #
    # ------------------------------------------------------------------ #
    def refresh_now(self, trigger_side_effects: bool = False) -> RefreshResult:
        """Fetch from the configured source, upsert, detect new events, prune.

        When ``trigger_side_effects`` is true (scheduled jobs and user-initiated
        refreshes), newly-detected relevant events fire notifications + webhook.
        Network/parse failures are caught and reported as a localized error key;
        previously cached events remain available, so the UI degrades gracefully.
        """
        source = get_source(self.config.get("source", "leekduck"))
        existing = self.db.existing_ids()
        try:
            events = source.fetch()
        except FetchError as exc:
            logger.warning("Fetch failed: %s", exc)
            return RefreshResult(False, error_key="errors.network")
        except ParseError as exc:
            logger.warning("Parse failed: %s", exc)
            return RefreshResult(False, error_key="errors.parse")
        except Exception:  # noqa: BLE001 - last-resort guard
            logger.exception("Unexpected refresh error")
            return RefreshResult(False, error_key="errors.generic")
        return self._apply_fetch(events, existing, trigger_side_effects)

    async def refresh_now_async(self, trigger_side_effects: bool = False) -> RefreshResult:
        """Async counterpart of :meth:`refresh_now` for the desktop GUI.

        Awaits the source's ``fetch_async`` (real async network I/O) and offloads
        the synchronous DB work to a thread, so the Tk main loop never blocks.
        """
        source = get_source(self.config.get("source", "leekduck"))
        existing = await asyncio.to_thread(self.db.existing_ids)
        try:
            events = await source.fetch_async()
        except FetchError as exc:
            logger.warning("Async fetch failed: %s", exc)
            return RefreshResult(False, error_key="errors.network")
        except ParseError as exc:
            logger.warning("Async parse failed: %s", exc)
            return RefreshResult(False, error_key="errors.parse")
        except Exception:  # noqa: BLE001 - last-resort guard
            logger.exception("Unexpected async refresh error")
            return RefreshResult(False, error_key="errors.generic")
        return await asyncio.to_thread(self._apply_fetch, events, existing, trigger_side_effects)

    def _apply_fetch(self, events, existing, trigger_side_effects: bool) -> RefreshResult:
        """Persist fetched events, detect new ones, prune, fire side effects."""
        with self._lock:
            count = self.db.upsert_events(events)
            self.db.prune_old(self.config.get("prune_after_days", 45))
        first_load = not existing
        new_events = [] if first_load else [e for e in events if e.event_id not in existing]
        result = RefreshResult(True, count=count, new_events=new_events, first_load=first_load)
        if trigger_side_effects and new_events:
            self._dispatch_new_events(new_events)
        return result

    def _scheduled_refresh(self) -> None:
        result = self.refresh_now(trigger_side_effects=True)
        if self.on_update:
            try:
                self.on_update(result)
            except Exception:  # noqa: BLE001 - callback must not break the job
                logger.exception("on_update callback failed")

    def _dispatch_new_events(self, new_events: list[Event]) -> None:
        """Fire notifications + webhook + Telegram for relevant new events."""
        relevant = [
            e for e in new_events
            if self._region_match(e) and e.status() in ("upcoming", "active")
        ]
        if self.config.get("notify_favorites_only", False):
            favs = set(self.favorite_types())
            relevant = [e for e in relevant if e.event_type in favs]
        if not relevant:
            return
        self._send_alert(relevant, self.t("notify.new_title"), self.t("notify.new_body", n=len(relevant)))

    def _check_reminders(self) -> None:
        """Alert once for events starting within the ``remind_before_minutes`` window.

        Runs every minute off the scheduler; reads only the local store. Honours
        the region filter (via ``get_events``) and notify-favorites-only, same as
        new-event alerts.
        """
        lead = int(self.config.get("remind_before_minutes", 0) or 0)
        if lead <= 0:
            return
        now = datetime.now()
        window_end = now + timedelta(minutes=lead)
        due = [
            e for e in self.get_events()
            if e.event_id not in self._reminded and e.start and now <= e.start <= window_end
        ]
        if self.config.get("notify_favorites_only", False):
            favs = set(self.favorite_types())
            due = [e for e in due if e.event_type in favs]
        if not due:
            return
        for e in due:
            # ponytail: in-memory dedup — may re-remind once if restarted mid-window;
            # persist the ID set if that ever matters.
            self._reminded.add(e.event_id)
        self._send_alert(due, self.t("notify.reminder_title"), self.t("notify.reminder_body", n=len(due)))

    def _check_update(self) -> None:
        """Check GitHub for a newer release; cache the result and notify the UI."""
        info = updates.check(__version__)
        if info and info != self._update_available:
            self._update_available = info
            logger.info("Update available: v%s", info["version"])
            if self.on_update_available:
                try:
                    self.on_update_available(info)
                except Exception:  # noqa: BLE001 - callback must not break the job
                    logger.exception("on_update_available callback failed")

    def latest_update(self) -> Optional[dict]:
        """The cached ``{version, url}`` of a newer release, or None if up to date."""
        return self._update_available

    def _send_alert(self, events: list[Event], title: str, body: str) -> None:
        """Fan an alert out to the enabled channels (desktop, webhook, Telegram)."""
        if self.config.get("notifications", True):
            notify(title, body)
        url = (self.config.get("webhook_url", "") or "").strip()
        if url:
            # Off-thread so a slow webhook never blocks the caller.
            threading.Thread(target=self._send_webhook, args=(url, events, title, body), daemon=True).start()
        if (self.config.get("telegram_bot_token", "") or "").strip() and \
                (self.config.get("telegram_chat_id", "") or "").strip():
            threading.Thread(target=self._send_telegram, args=(events, body), daemon=True).start()

    def _send_telegram(self, events: list[Event], body: str) -> tuple[bool, str]:
        lines = [body]
        for e in events[:10]:
            line = f"• {e.name}"
            if e.link:
                line += f"\n{e.link}"
            lines.append(line)
        return telegram.send(
            self.config.get("telegram_bot_token", ""),
            self.config.get("telegram_chat_id", ""),
            "\n".join(lines),
        )

    def _send_webhook(self, url: str, events: list[Event], title: str, body: str) -> tuple[bool, str]:
        payload = [self._webhook_event(e) for e in events]
        return webhook.send(url, title, body, payload, secret=self._webhook_secret())

    def _webhook_secret(self) -> Optional[str]:
        return (self.config.get("webhook_secret", "") or "").strip() or None

    def _webhook_event(self, event: Event) -> dict:
        return {
            "name": event.name,
            "link": event.link,
            "region": self.t(f"regions.{event.region}"),
            "type": event.type_label,
            "description": self.description(event),
            "start": self.format_time(event.start),
            "end": self.format_time(event.end),
        }

    def send_test_webhook(self, url: str) -> tuple[bool, str]:
        """Send a sample payload to verify a user-entered webhook URL works."""
        url = (url or "").strip()
        if not url:
            return False, "no url"
        sample = [{
            "name": f"{self.t('app.title')} — test",
            "link": "",
            "region": self.t("regions.Global"),
            "description": self.t("app.subtitle"),
        }]
        return webhook.send(
            url, self.t("notify.new_title"), self.t("app.subtitle"), sample,
            secret=self._webhook_secret(),
        )

    # ------------------------------------------------------------------ #
    # Queries                                                            #
    # ------------------------------------------------------------------ #
    def get_events(
        self,
        statuses: Optional[list[str]] = None,
        search: Optional[str] = None,
        event_types: Optional[list[str]] = None,
        limit: Optional[int] = None,
        use_filter: bool = True,
        favorites_only: bool = False,
    ) -> list[Event]:
        """Return events, applying the user's region filter by default.

        Semantics: an event is shown when it is Global *or* its region is one the
        user selected.  Optional ``search`` and ``event_types`` narrow further;
        ``favorites_only`` keeps only events whose type is favorited.
        """
        regions = self.config.get("regions", [GLOBAL]) if use_filter else None
        if regions == []:  # empty selection => no region filter (show everything)
            regions = None
        events = self.db.get_events(
            regions=regions, statuses=statuses, event_types=event_types,
            search=search, limit=limit,
        )
        if favorites_only:
            favs = set(self.favorite_types())
            events = [e for e in events if e.event_type in favs]
        return events

    def available_types(self) -> list[str]:
        """Raw event types present in the store (for the type filter dropdown)."""
        return self.db.distinct_types()

    def last_updated(self) -> Optional[datetime]:
        raw = self.db.last_updated()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def stats(self) -> dict[str, int]:
        """Counts for the current (filtered) view: live / upcoming / total."""
        events = self.get_events()
        live = sum(1 for e in events if e.status() == "active")
        upcoming = sum(1 for e in events if e.status() == "upcoming")
        return {"live": live, "upcoming": upcoming, "total": len(events)}

    # ------------------------------------------------------------------ #
    # Localized display helpers                                          #
    # ------------------------------------------------------------------ #
    def countdown(self, event: Event) -> str:
        """A localized relative-time string for the event's current state."""
        now = datetime.now()
        status = event.status(now)
        if status == "upcoming" and event.start:
            return self.t("events.starts_in", time=self._humanize(event.start - now))
        if status == "active" and event.end:
            return self.t("events.ends_in", time=self._humanize(event.end - now))
        if status == "ended":
            return self.t("events.ended")
        return ""

    def _humanize(self, delta: timedelta) -> str:
        secs = max(0, int(delta.total_seconds()))
        days, rem = divmod(secs, 86_400)
        hours, rem = divmod(rem, 3_600)
        minutes = rem // 60
        if days >= 1:
            return self.t("time.day", n=days)
        if hours >= 1:
            return self.t("time.hour", n=hours)
        if minutes >= 1:
            return self.t("time.minute", n=minutes)
        return self.t("time.now")

    def description(self, event: Event) -> str:
        """A localized one-line summary built from the event's highlights.

        The feed has no prose description, so we compose one from the heading and
        structured extras (raid bosses, promo codes, spawn/research flags). The
        connector labels come from ``languages.json``; the names themselves come
        from the source.
        """
        parts: list[str] = []
        if event.heading:
            parts.append(event.heading if event.heading.endswith((".", "!", "?")) else event.heading + ".")
        if event.bosses:
            parts.append(self.t("desc.featured_raids", names=", ".join(event.bosses[:6])))
        if event.promocodes:
            parts.append(self.t("desc.promo", codes=", ".join(event.promocodes[:3])))
        flags: list[str] = []
        if event.has_spawns:
            flags.append(self.t("desc.spawns"))
        if event.has_research:
            flags.append(self.t("desc.research"))
        if flags:
            parts.append(self.t("desc.includes", items="、".join(flags) if self._is_cjk() else ", ".join(flags)))
        return " ".join(p for p in parts if p).strip()

    def _is_cjk(self) -> bool:
        return self.translator.language.startswith("zh")

    def format_time(self, dt) -> str:
        """Format an event time honouring the time_format + display_timezone settings.

        Source times are naive local; if a display timezone is set we interpret
        them as system-local and convert. Falls back gracefully on any error.
        """
        if not dt:
            return "—"
        tz_name = (self.config.get("display_timezone", "") or "").strip()
        if tz_name:
            try:
                from zoneinfo import ZoneInfo
                dt = dt.astimezone().astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
            except Exception:  # noqa: BLE001 - bad tz name => show local time
                pass
        fmt = "%b %d, %Y · %I:%M %p" if self.config.get("time_format") == "12h" else "%b %d, %Y · %H:%M"
        return dt.strftime(fmt)

    # ------------------------------------------------------------------ #
    # Favorites (favorited event types)                                  #
    # ------------------------------------------------------------------ #
    def favorite_types(self) -> list[str]:
        return list(self.config.get("favorite_types", []) or [])

    def is_favorite(self, event_type: str) -> bool:
        return event_type in self.favorite_types()

    def toggle_favorite(self, event_type: str) -> bool:
        """Star/unstar an event type. Returns the new favorited state."""
        favs = self.favorite_types()
        if event_type in favs:
            favs.remove(event_type)
        elif event_type:
            favs.append(event_type)
        self.config.set("favorite_types", favs)
        return event_type in favs

    # ------------------------------------------------------------------ #
    # Calendar export                                                    #
    # ------------------------------------------------------------------ #
    def calendar_ics(self, events: Optional[list[Event]] = None) -> str:
        """An iCalendar (.ics) document for the given (or current filtered) events."""
        events = events if events is not None else self.get_events()
        return ical.build_ics(events, name=self.t("app.title"), describe=self.description)

    def export_calendar(self, path: str | Path, events: Optional[list[Event]] = None) -> str:
        Path(path).write_text(self.calendar_ics(events), encoding="utf-8")
        logger.info("Exported calendar to %s", path)
        return str(path)

    # ------------------------------------------------------------------ #
    # Settings                                                           #
    # ------------------------------------------------------------------ #
    def set_language(self, code: str) -> None:
        self.translator.set_language(code)
        self.config.set("language", self.translator.language)

    def set_regions(self, regions: list[str]) -> None:
        self.config.set("regions", regions or [GLOBAL])

    def set_interval(self, minutes: int) -> None:
        minutes = max(1, int(minutes))
        self.config.set("refresh_interval_minutes", minutes)
        self._scheduler.reschedule(minutes)

    def set_notifications(self, enabled: bool) -> None:
        self.config.set("notifications", bool(enabled))

    def set_webhook(self, url: str) -> None:
        self.config.set("webhook_url", (url or "").strip())

    def set_webhook_secret(self, secret: str) -> None:
        self.config.set("webhook_secret", (secret or "").strip())

    def set_notify_favorites_only(self, enabled: bool) -> None:
        self.config.set("notify_favorites_only", bool(enabled))

    def set_remind_before(self, minutes) -> None:
        try:
            self.config.set("remind_before_minutes", max(0, int(minutes)))
        except (TypeError, ValueError):
            pass

    def set_telegram(self, token: str, chat_id: str) -> None:
        self.config.set("telegram_bot_token", (token or "").strip(), save=False)
        self.config.set("telegram_chat_id", (chat_id or "").strip())

    def set_time_format(self, fmt: str) -> None:
        self.config.set("time_format", "12h" if fmt == "12h" else "24h")

    def set_display_timezone(self, tz_name: str) -> None:
        self.config.set("display_timezone", (tz_name or "").strip())

    def set_close_to_tray(self, enabled: bool) -> None:
        self.config.set("close_to_tray", bool(enabled))

    # ------------------------------------------------------------------ #
    # Config import / export                                             #
    # ------------------------------------------------------------------ #
    def export_config(self, path: str | Path) -> str:
        """Write the current settings to ``path`` as pretty JSON. Returns path."""
        path = Path(path)
        path.write_text(
            json.dumps(self.config.data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Exported config to %s", path)
        return str(path)

    def export_config_json(self) -> str:
        """Return the current settings as a JSON string (for web download)."""
        return json.dumps(self.config.data, indent=2, ensure_ascii=False)

    def import_config(self, source: "str | Path | dict") -> tuple[bool, str]:
        """Import settings from a file path, a JSON string, or a dict.

        Settings are deep-merged over the current config and persisted, then the
        runtime bits that depend on config (language, scheduler interval) are
        re-applied immediately. Returns ``(ok, detail)``.
        """
        try:
            if isinstance(source, dict):
                data = source
            else:
                text = (
                    Path(source).read_text(encoding="utf-8")
                    if Path(str(source)).exists()
                    else str(source)
                )
                data = json.loads(text)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Config import failed: %s", exc)
            return False, str(exc)
        if not isinstance(data, dict):
            return False, "config must be a JSON object"

        self.config.update(data)
        # Re-apply settings that affect running components right away.
        self.translator.set_language(self.config.get("language", "en"))
        self._scheduler.reschedule(self.config.get("refresh_interval_minutes", 60))
        logger.info("Imported config (%d top-level keys)", len(data))
        return True, "ok"

    def _region_match(self, event: Event) -> bool:
        regions = self.config.get("regions", [GLOBAL])
        if not regions:
            return True
        return event.region == GLOBAL or event.region in regions

    # Convenience pass-through so UIs can call ``service.t(...)`` directly.
    def t(self, key: str, **kwargs) -> str:
        return self.translator.t(key, **kwargs)
