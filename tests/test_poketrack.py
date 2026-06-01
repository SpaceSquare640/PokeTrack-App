"""PokéTrack test suite — deterministic, offline (no real network).

Run from the project root:

    python -m pytest -q

Uses temp directories for config/DB and a FakeSource, so nothing here touches
your real config.json or data/ — and no HTTP requests are made.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import poketrack.core.service as service_module
from poketrack.app_context import ROOT
from poketrack.config import Config
from poketrack.core.database import Database
from poketrack.core.models import Event, _parse_dt
from poketrack.core.regions import classify
from poketrack.core.service import PokeTrackService
from poketrack.i18n import Translator


# --------------------------------------------------------------------------- #
# Helpers / fixtures                                                          #
# --------------------------------------------------------------------------- #
class FakeSource:
    """A source that returns a fixed list of events — no network."""

    name = "fake"

    def __init__(self, events):
        self._events = events

    def fetch(self):
        return list(self._events)

    async def fetch_async(self):
        return list(self._events)


def make_event(eid, name, *, region="Global", etype="community-day",
               start=None, end=None) -> Event:
    return Event(event_id=eid, name=name, event_type=etype, region=region,
                 start=start, end=end, link=f"https://x/{eid}")


@pytest.fixture
def service(tmp_path):
    cfg = Config(tmp_path / "config.json")
    tr = Translator(ROOT / "languages.json", "en")
    db = Database(tmp_path / "poketrack.db")
    return PokeTrackService(cfg, tr, db)


# --------------------------------------------------------------------------- #
# i18n                                                                        #
# --------------------------------------------------------------------------- #
def test_i18n_three_languages_and_fallback():
    tr = Translator(ROOT / "languages.json", "en")
    assert set(tr.available_languages()) == {"en", "zh-Hant", "zh-Hans"}
    assert tr.t("events.view_details") == "View Details"
    tr.set_language("zh-Hant")
    assert tr.t("settings.title") == "設定"
    tr.set_language("zh-Hans")
    assert tr.t("settings.title") == "设置"
    # placeholder + graceful fallbacks
    assert "5" in tr.t("events.count", n=5)
    assert tr.t("does.not.exist") == "does.not.exist"


# --------------------------------------------------------------------------- #
# Regions                                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("Safari Zone: Taipei", "Asia"),
    ("GO Tour: Los Angeles", "North America"),
    ("City Safari: São Paulo", "South America"),
    ("January Community Day", "Global"),
    ("Sydney Safari Zone", "Oceania"),
])
def test_region_classifier(text, expected):
    assert classify(text) == expected


# --------------------------------------------------------------------------- #
# Models                                                                      #
# --------------------------------------------------------------------------- #
def test_parse_dt_normalises_to_naive():
    assert _parse_dt("2024-05-19T14:00:00.000").tzinfo is None
    assert _parse_dt("2024-01-01T00:00:00Z").tzinfo is None          # was a crash source
    assert _parse_dt("2024-01-01T00:00:00+09:00").tzinfo is None
    assert _parse_dt("not-a-date") is None


def test_event_status_and_type_label():
    now = datetime.now()
    live = make_event("a", "Live", start=now - timedelta(hours=1), end=now + timedelta(hours=1))
    soon = make_event("b", "Soon", start=now + timedelta(days=1), end=now + timedelta(days=2))
    done = make_event("c", "Done", start=now - timedelta(days=2), end=now - timedelta(days=1))
    assert live.status() == "active"
    assert soon.status() == "upcoming"
    assert done.status() == "ended"
    assert live.type_label == "Community Day"


# --------------------------------------------------------------------------- #
# Database                                                                     #
# --------------------------------------------------------------------------- #
def test_db_upsert_dedupe_and_filters(tmp_path):
    db = Database(tmp_path / "t.db")
    now = datetime.now()
    rows = [
        make_event("g", "Global Fest", region="Global", etype="live-event",
                   start=now, end=now + timedelta(hours=2)),
        make_event("a", "Asia Safari", region="Asia", etype="safari-zone",
                   start=now + timedelta(days=1), end=now + timedelta(days=2)),
    ]
    assert db.upsert_events(rows) == 2
    assert db.upsert_events(rows) == 2 and db.count() == 2          # no duplicates
    # region filter always unions Global
    regions = {e.region for e in db.get_events(regions=["Asia"])}
    assert regions == {"Global", "Asia"}
    # type + search filters
    assert [e.event_id for e in db.get_events(event_types=["safari-zone"])] == ["a"]
    assert [e.event_id for e in db.get_events(search="global")] == ["g"]
    assert db.existing_ids() == {"g", "a"}
    assert "safari-zone" in db.distinct_types()


def test_db_prune_old(tmp_path):
    db = Database(tmp_path / "p.db")
    now = datetime.now()
    db.upsert_events([
        make_event("old", "Old", end=now - timedelta(days=100)),
        make_event("recent", "Recent", end=now - timedelta(days=1)),
        make_event("future", "Future", end=now + timedelta(days=5)),
    ])
    assert db.prune_old(45) == 1               # only "old" removed
    assert db.existing_ids() == {"recent", "future"}


# --------------------------------------------------------------------------- #
# Service                                                                      #
# --------------------------------------------------------------------------- #
def test_region_filter_semantics(service):
    now = datetime.now()
    service.db.upsert_events([
        make_event("g", "Glob", region="Global", start=now, end=now + timedelta(hours=1)),
        make_event("a", "Asi", region="Asia", start=now, end=now + timedelta(hours=1)),
        make_event("e", "Eur", region="Europe", start=now, end=now + timedelta(hours=1)),
    ])
    service.set_regions(["Global"])
    assert {e.region for e in service.get_events()} == {"Global"}
    service.set_regions(["Asia"])
    assert {e.region for e in service.get_events()} == {"Global", "Asia"}


def test_countdown_strings(service):
    now = datetime.now()
    soon = make_event("s", "Soon", start=now + timedelta(hours=3, minutes=5), end=now + timedelta(days=1))
    live = make_event("l", "Live", start=now - timedelta(hours=1), end=now + timedelta(days=2, hours=1))
    done = make_event("d", "Done", start=now - timedelta(days=3), end=now - timedelta(days=1))
    assert "3h" in service.countdown(soon)
    assert "2d" in service.countdown(live)
    assert service.countdown(done) == "Ended"


def test_refresh_detects_new_events(service, monkeypatch):
    now = datetime.now()
    e1 = make_event("1", "First", start=now + timedelta(days=1), end=now + timedelta(days=2))
    e2 = make_event("2", "Second", start=now + timedelta(days=1), end=now + timedelta(days=2))

    holder = {"events": [e1]}
    monkeypatch.setattr(service_module, "get_source", lambda name: FakeSource(holder["events"]))

    first = service.refresh_now()
    assert first.ok and first.first_load and first.new_count == 0   # don't flag all as new

    holder["events"] = [e1, e2]
    second = service.refresh_now()
    assert second.ok and not second.first_load
    assert [e.event_id for e in second.new_events] == ["2"]


# --------------------------------------------------------------------------- #
# Web                                                                          #
# --------------------------------------------------------------------------- #
def test_web_renders_and_filters(service):
    from poketrack.web.server import create_app
    now = datetime.now()
    service.db.upsert_events([
        make_event("cd", "Community Day", region="Global", etype="community-day",
                   start=now, end=now + timedelta(hours=3)),
        make_event("rh", "Raid Hour", region="Global", etype="raid-hour",
                   start=now + timedelta(days=1), end=now + timedelta(days=1, hours=1)),
    ])
    client = create_app(service).test_client()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Community Activity Monitor" in html      # English subtitle
    assert "#0B1120" in html                          # palette injected
    assert "Community Day" in html and "Raid Hour" in html

    # search filter narrows the grid (check the card <h3>, not the type dropdown
    # which always lists every type as an <option>).
    filtered = client.get("/?q=raid").get_data(as_text=True)
    assert "Raid Hour</h3>" in filtered and "Community Day</h3>" not in filtered

    # JSON API + language switch (offline; no /api/refresh network call here)
    api = client.get("/api/events").get_json()
    assert isinstance(api, list) and len(api) == 2
    client.post("/set-language", data={"language": "zh-Hant"})
    assert "社群活動監測器" in client.get("/").get_data(as_text=True)


# --------------------------------------------------------------------------- #
# Descriptions + highlights                                                   #
# --------------------------------------------------------------------------- #
def test_event_highlights_and_description(service):
    item = {
        "eventID": "x", "name": "Raid Battles", "eventType": "raid-battles",
        "heading": "Raid Battles", "link": "https://x",
        "start": "2099-01-01T00:00:00.000", "end": "2099-01-02T00:00:00.000",
        "extraData": {
            "raidbattles": {"bosses": [{"name": "Tapu Fini"}, {"name": "Mewtwo"}]},
            "promocodes": ["FREESTUFF"],
            "generic": {"hasSpawns": True, "hasFieldResearchTasks": False},
        },
    }
    e = Event.from_scrapedduck(item)
    assert e.bosses == ["Tapu Fini", "Mewtwo"]
    assert e.promocodes == ["FREESTUFF"]
    assert e.has_spawns and not e.has_research
    desc = service.description(e)
    assert "Tapu Fini" in desc and "FREESTUFF" in desc and "increased wild spawns" in desc


def test_db_extra_roundtrip(tmp_path):
    db = Database(tmp_path / "x.db")
    e = make_event("r", "Raids")
    e.bosses = ["Tapu Fini"]
    e.promocodes = ["ABC"]
    e.has_spawns = True
    db.upsert_events([e])
    back = db.get_event("r")
    assert back.bosses == ["Tapu Fini"] and back.promocodes == ["ABC"] and back.has_spawns


# --------------------------------------------------------------------------- #
# Webhook payloads (pure functions; no network)                               #
# --------------------------------------------------------------------------- #
def test_webhook_payload_building():
    from poketrack.core import webhook
    evs = [{"name": "CD", "link": "https://x/cd", "description": "Community Day", "region": "Global"}]

    discord, prov = webhook.build_payload("https://discord.com/api/webhooks/1/abc", "T", "msg", evs)
    assert prov == "discord" and discord["embeds"][0]["title"] == "CD"

    slack, prov = webhook.build_payload("https://hooks.slack.com/services/x", "T", "msg", evs)
    assert prov == "slack" and "CD" in slack["text"]

    generic, prov = webhook.build_payload("https://example.com/hook", "T", "msg", evs)
    assert prov == "generic" and generic["events"] == evs and generic["title"] == "T"


def test_webhook_hmac_sign_and_verify():
    from poketrack.core import webhook
    body = b'{"hello":"world"}'
    sig = webhook.sign("s3cret", body)
    assert sig.startswith("sha256=")
    assert webhook.verify_signature("s3cret", body, sig)            # correct secret
    assert not webhook.verify_signature("wrong", body, sig)          # wrong secret
    assert not webhook.verify_signature("s3cret", body, "sha256=00") # tampered sig
    assert not webhook.verify_signature("", body, sig)               # no secret


# --------------------------------------------------------------------------- #
# Async refresh (Task 1b)                                                     #
# --------------------------------------------------------------------------- #
def test_async_refresh_detects_new(service, monkeypatch):
    import asyncio
    now = datetime.now()
    e1 = make_event("1", "First", start=now + timedelta(days=1), end=now + timedelta(days=2))
    e2 = make_event("2", "Second", start=now + timedelta(days=1), end=now + timedelta(days=2))
    holder = {"events": [e1]}
    monkeypatch.setattr(service_module, "get_source", lambda name: FakeSource(holder["events"]))

    first = asyncio.run(service.refresh_now_async())
    assert first.ok and first.first_load and first.new_count == 0

    holder["events"] = [e1, e2]
    second = asyncio.run(service.refresh_now_async())
    assert second.ok and [e.event_id for e in second.new_events] == ["2"]


# --------------------------------------------------------------------------- #
# Scheduler re-scheduling integration (Task 3a)                               #
# --------------------------------------------------------------------------- #
def test_scheduler_reschedules_on_interval_change(service, monkeypatch):
    from poketrack.core.scheduler import UpdateScheduler
    # Guard against the (improbable) job firing mid-test: no real network.
    monkeypatch.setattr(service_module, "get_source", lambda name: FakeSource([]))
    service._scheduler.start()
    try:
        sched = service._scheduler._scheduler
        job = sched.get_job(UpdateScheduler.JOB_ID)
        assert job is not None
        assert job.trigger.interval == timedelta(minutes=60)   # fixture default
        service.set_interval(15)                                # update config + reschedule
        job = sched.get_job(UpdateScheduler.JOB_ID)
        assert job.trigger.interval == timedelta(minutes=15)
        assert service.config.get("refresh_interval_minutes") == 15
    finally:
        service._scheduler.stop()


# --------------------------------------------------------------------------- #
# Config import / export (Task 2a)                                            #
# --------------------------------------------------------------------------- #
def test_config_export_and_import(service, tmp_path):
    service.config.set("webhook_url", "https://example.com/hook")
    path = tmp_path / "exp.json"
    service.export_config(path)
    assert path.exists()

    service.config.set("webhook_url", "https://changed")          # mutate…
    ok, _ = service.import_config(path)                           # …then restore from file
    assert ok and service.config.get("webhook_url") == "https://example.com/hook"

    # import from a dict re-applies language immediately
    ok, _ = service.import_config({"language": "zh-Hant"})
    assert ok and service.translator.language == "zh-Hant"


# --------------------------------------------------------------------------- #
# Externalised region map (Task 1a)                                           #
# --------------------------------------------------------------------------- #
def test_regions_loaded_from_external_map():
    from poketrack.core import regions
    assert "Asia" in regions.REGIONS and "Europe" in regions.REGIONS
    assert regions.classify("Safari Zone: Tokyo") == "Asia"
    regions.reload()  # re-read the JSON at runtime without error
    assert regions.classify("GO Tour: London") == "Europe"
