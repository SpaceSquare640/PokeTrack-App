"""Flask web front-end.

Mirrors the desktop app feature-for-feature using the *same* service, the *same*
``languages.json`` catalog, and the *same* Midnight Blue palette (injected into
the page so the two UIs are pixel-identical).

Routes
------
* ``GET  /``              — dashboard (event grid, search/type/region filters)
* ``POST /set-language``  — change UI language
* ``POST /set-regions``   — change region filter
* ``POST /api/refresh``   — trigger a fetch, returns JSON {ok, count, new, message}
* ``GET  /api/events``    — current (filtered) events as JSON
"""
from __future__ import annotations

import logging

from flask import (
    Flask, Response, jsonify, redirect, render_template, request, url_for,
)

from ..core.regions import REGIONS
from ..core.service import PokeTrackService
from ..gui.theme import MIDNIGHT_BLUE, status_color  # shared palette (no Tk import)

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
            "regions_all": REGIONS,
            "selected_regions": service.config.get("regions", ["Global"]),
        }

    def _filtered_events(q: str, type_filter: str):
        return service.get_events(
            search=q or None,
            event_types=[type_filter] if type_filter else None,
        )

    @app.route("/")
    def index():
        q = request.args.get("q", "").strip()
        type_filter = request.args.get("type", "").strip()
        events = _filtered_events(q, type_filter)
        last = service.last_updated()
        return render_template(
            "index.html",
            events=[_view_model(e, service) for e in events],
            stats=_stats(events),
            types=[(tp, tp.replace("-", " ").title()) for tp in service.available_types()],
            current_type=type_filter,
            query=q,
            last_updated=last.strftime("%b %d, %Y · %H:%M") if last else "—",
            **base_context(),
        )

    @app.post("/set-language")
    def set_language():
        service.set_language(request.form.get("language", "en"))
        return redirect(url_for("index"))

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
        return jsonify({
            "ok": result.ok,
            "count": result.count,
            "new": result.new_count,
            "message": message,
        })

    @app.get("/api/events")
    def api_events():
        q = request.args.get("q", "").strip()
        type_filter = request.args.get("type", "").strip()
        return jsonify([_view_model(e, service) for e in _filtered_events(q, type_filter)])

    # ------------------------------------------------------------------ #
    # Settings page (mirrors the desktop Settings tab)                   #
    # ------------------------------------------------------------------ #
    @app.get("/settings")
    def settings():
        cfg = service.config
        return render_template(
            "settings.html",
            status=request.args.get("status", ""),
            webhook_url=cfg.get("webhook_url", ""),
            webhook_secret=cfg.get("webhook_secret", ""),
            interval=cfg.get("refresh_interval_minutes", 60),
            notifications=cfg.get("notifications", True),
            source=cfg.get("source", "leekduck"),
            **base_context(),
        )

    @app.post("/settings")
    def settings_save():
        service.set_webhook(request.form.get("webhook_url", ""))
        service.set_webhook_secret(request.form.get("webhook_secret", ""))
        service.set_notifications("notifications" in request.form)
        source = request.form.get("source", "leekduck")
        if source in ("leekduck", "blog"):
            service.config.set("source", source)
        try:
            service.set_interval(int(request.form.get("refresh_interval_minutes", 60)))
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
    badge_keys = {
        "active": "events.active_badge",
        "upcoming": "events.upcoming_badge",
        "ended": "events.ended_badge",
    }
    data["badge"] = service.t(badge_keys[status]) if status in badge_keys else ""
    return data
