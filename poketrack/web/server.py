"""Flask web front-end.

Mirrors the desktop app feature-for-feature using the *same* service, the *same*
``languages.json`` catalog, and the *same* Midnight Blue palette (injected into
the page so the two UIs are pixel-identical).

Routes
------
* ``GET  /``                 — dashboard (search/type/region/favorites filters)
* ``GET  /event/<id>``       — event detail page
* ``GET  /calendar.ics``     — subscribable iCalendar feed (honours filters/?id=)
* ``POST /favorite``         — toggle a favorited event type
* ``GET/POST /settings``     — settings page (+ /settings/export, /settings/import)
* ``POST /api/refresh`` · ``GET /api/events``
"""
from __future__ import annotations

import logging

from flask import (
    Flask, Response, abort, jsonify, redirect, render_template, request, url_for,
)

from .. import __version__
from ..core.regions import REGIONS
from ..core.service import PokeTrackService
from ..gui.theme import MIDNIGHT_BLUE, PAPER_LIGHT, status_color  # shared palettes (no Tk import)

logger = logging.getLogger(__name__)


def create_app(service: PokeTrackService) -> Flask:
    app = Flask(__name__)

    def base_context() -> dict:
        translator = service.translator
        return {
            "t": translator.t,
            "lang": translator.language,
            "languages": translator.available_languages(),
            "language_name": translator.language_name,
            "palette": MIDNIGHT_BLUE,
            "palette_light": PAPER_LIGHT,
            "version": __version__,
            "regions_all": REGIONS,
            "selected_regions": service.config.get("regions", ["Global"]),
            "update": service.latest_update(),
            "github_profile_url": "https://github.com/SpaceSquare640",
            "discord_url": "https://discord.gg/aaUQVJeCgC",
        }

    def _filtered(q: str, type_filter: str, favorites_only: bool, status: str = ""):
        return service.get_events(
            search=q or None,
            event_types=[type_filter] if type_filter else None,
            statuses=[status] if status else None,
            favorites_only=favorites_only,
        )

    @app.route("/")
    def index():
        q = request.args.get("q", "").strip()
        type_filter = request.args.get("type", "").strip()
        status = request.args.get("status", "").strip()
        fav = request.args.get("fav") == "1"
        events = _filtered(q, type_filter, fav, status)
        last = service.last_updated()
        vms = [_view_model(e, service) for e in events]
        pairs = list(zip(events, vms))

        # Fusion layout: sections — live first, upcoming grouped by start date,
        # then unknown, then past (most recent first).
        active = [vm for _e, vm in pairs if vm["status"] == "active"]
        ended = [vm for _e, vm in pairs if vm["status"] == "ended"]
        other = [vm for _e, vm in pairs if vm["status"] == "unknown"]
        groups: list[tuple[str, list]] = []
        if active:
            groups.append((service.t("events.section_active"), active))
        by_day: dict[str, list] = {}
        for e, vm in pairs:  # events arrive sorted by start ASC
            if vm["status"] == "upcoming":
                label = e.start.strftime("%b %d, %Y") if e.start else service.t("events.section_upcoming")
                by_day.setdefault(label, []).append(vm)
        groups.extend(by_day.items())
        if other:
            groups.append((service.t("events.section_other"), other))
        if ended:
            groups.append((service.t("events.section_past"), list(reversed(ended))))

        # Hero: the headline live event, only on the default (unfiltered) view.
        hero = active[0] if active and not (q or type_filter or status or fav) else None

        return render_template(
            "index.html",
            events=vms,
            groups=groups,
            hero=hero,
            kpi_fav=sum(1 for vm in vms if vm["favorite"]),
            active_nav="fav" if fav else "events",
            stats=_stats(events),
            types=[(tp, tp.replace("-", " ").title()) for tp in service.available_types()],
            current_type=type_filter,
            current_status=status,
            query=q,
            favorites_only=fav,
            last_updated=service.format_time(last) if last else "—",
            **base_context(),
        )

    @app.get("/sw.js")
    def service_worker():
        # Served from root so the SW scope covers the whole app (not just /static).
        resp = app.send_static_file("sw.js")
        resp.headers["Service-Worker-Allowed"] = "/"
        return resp

    @app.get("/event/<path:event_id>")
    def event_detail(event_id: str):
        event = service.db.get_event(event_id)
        if not event:
            abort(404)
        return render_template("event.html", event=_view_model(event, service),
                               active_nav="events", **base_context())

    @app.get("/calendar.ics")
    def calendar_ics():
        event_id = request.args.get("id", "").strip()
        if event_id:
            one = service.db.get_event(event_id)
            events = [one] if one else []
        else:
            events = _filtered(
                request.args.get("q", "").strip(),
                request.args.get("type", "").strip(),
                request.args.get("fav") == "1",
                request.args.get("status", "").strip(),
            )
        return Response(
            service.calendar_ics(events),
            mimetype="text/calendar",
            headers={"Content-Disposition": "attachment; filename=poketrack.ics"},
        )

    @app.post("/favorite")
    def favorite():
        service.toggle_favorite(request.form.get("type", "").strip())
        return redirect(request.referrer or url_for("index"))

    @app.post("/api/favorite")
    def api_favorite():
        """JSON favorite toggle (used by the TS front-end; no page reload)."""
        etype = request.form.get("type", "").strip()
        fav = service.toggle_favorite(etype) if etype else False
        return jsonify({"type": etype, "favorite": fav})

    @app.post("/set-language")
    def set_language():
        service.set_language(request.form.get("language", "en"))
        return redirect(request.referrer or url_for("index"))

    @app.post("/set-regions")
    def set_regions():
        service.set_regions(request.form.getlist("regions"))
        return redirect(url_for("index"))

    @app.post("/api/refresh")
    def api_refresh():
        result = service.refresh_now(trigger_side_effects=True)
        message = service.t("status.updated") if result.ok else service.t(
            result.error_key or "errors.generic"
        )
        return jsonify({"ok": result.ok, "count": result.count, "new": result.new_count, "message": message})

    @app.get("/api/events")
    def api_events():
        q = request.args.get("q", "").strip()
        type_filter = request.args.get("type", "").strip()
        status = request.args.get("status", "").strip()
        fav = request.args.get("fav") == "1"
        return jsonify([_view_model(e, service) for e in _filtered(q, type_filter, fav, status)])

    # ------------------------------------------------------------------ #
    # Settings                                                           #
    # ------------------------------------------------------------------ #
    @app.get("/settings")
    def settings():
        cfg = service.config
        return render_template(
            "settings.html",
            active_nav="settings",
            status=request.args.get("status", ""),
            webhook_url=cfg.get("webhook_url", ""),
            webhook_secret=cfg.get("webhook_secret", ""),
            interval=cfg.get("refresh_interval_minutes", 60),
            remind_before=cfg.get("remind_before_minutes", 15),
            notifications=cfg.get("notifications", True),
            notify_favorites_only=cfg.get("notify_favorites_only", False),
            telegram_token=cfg.get("telegram_bot_token", ""),
            telegram_chat=cfg.get("telegram_chat_id", ""),
            time_format=cfg.get("time_format", "24h"),
            timezone=cfg.get("display_timezone", ""),
            source=cfg.get("source", "leekduck"),
            favorite_types=service.favorite_types(),
            **base_context(),
        )

    @app.post("/settings")
    def settings_save():
        f = request.form
        service.set_webhook(f.get("webhook_url", ""))
        service.set_webhook_secret(f.get("webhook_secret", ""))
        service.set_notifications("notifications" in f)
        service.set_notify_favorites_only("notify_favorites_only" in f)
        service.set_telegram(f.get("telegram_token", ""), f.get("telegram_chat", ""))
        service.set_time_format(f.get("time_format", "24h"))
        service.set_display_timezone(f.get("timezone", ""))
        service.set_remind_before(f.get("remind_before_minutes", 15))
        if f.get("source") in ("leekduck", "blog"):
            service.config.set("source", f.get("source"))
        try:
            service.set_interval(int(f.get("refresh_interval_minutes", 60)))
        except (TypeError, ValueError):
            pass
        return redirect(url_for("settings", status="saved"))

    @app.get("/settings/export")
    def settings_export():
        return Response(
            service.export_config_json(),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=poketrack-config.json"},
        )

    @app.post("/settings/import")
    def settings_import():
        file = request.files.get("file")
        if not file:
            return redirect(url_for("settings", status="import_failed"))
        try:
            ok, _ = service.import_config(file.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            ok = False
        return redirect(url_for("settings", status="imported" if ok else "import_failed"))

    return app


def _stats(events) -> dict:
    live = sum(1 for e in events if e.status() == "active")
    upcoming = sum(1 for e in events if e.status() == "upcoming")
    return {"live": live, "upcoming": upcoming, "total": len(events)}


def _view_model(event, service: PokeTrackService) -> dict:
    """Augment an Event dict with translated, presentation-ready fields."""
    data = event.to_dict()
    status = data["status"]
    data["status_color"] = status_color(status)
    data["region_label"] = service.t(f"regions.{event.region}")
    data["countdown"] = service.countdown(event)
    data["description"] = service.description(event)
    data["start_display"] = service.format_time(event.start)
    data["end_display"] = service.format_time(event.end)
    data["favorite"] = service.is_favorite(event.event_type)
    data["bosses"] = event.bosses
    data["promocodes"] = event.promocodes
    data["has_spawns"] = event.has_spawns
    data["has_research"] = event.has_research
    badge_keys = {
        "active": "events.active_badge",
        "upcoming": "events.upcoming_badge",
        "ended": "events.ended_badge",
    }
    data["badge"] = service.t(badge_keys[status]) if status in badge_keys else ""
    return data
