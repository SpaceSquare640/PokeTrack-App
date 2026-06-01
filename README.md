# PokéTrack

[![CI](https://github.com/SpaceSquare640/PokeTrack-App/actions/workflows/ci.yml/badge.svg)](https://github.com/SpaceSquare640/PokeTrack-App/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/SpaceSquare640/PokeTrack-App)](https://github.com/SpaceSquare640/PokeTrack-App/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A community-activity monitor for **Pokémon GO**. It fetches upcoming and live
events, stores them locally, and shows them through **two interfaces that share
one design system** — a CustomTkinter desktop app and a Flask web app, both in a
consistent *Midnight Blue* dark theme.

> [!IMPORTANT]
> **Unofficial fan project.** PokéTrack is **not** affiliated with, endorsed by,
> or sponsored by Niantic, Nintendo, The Pokémon Company, or Leek Duck. "Pokémon"
> and "Pokémon GO" are trademarks of their respective owners, used here for
> identification only. Event data is sourced from [Leek Duck](https://leekduck.com)
> via [ScrapedDuck](https://github.com/bigfoott/ScrapedDuck) for **informational,
> non-commercial** use. Software provided **"AS IS"**, without warranty. See
> **[DISCLAIMER.md](DISCLAIMER.md)** and **[LICENSE](LICENSE)**.

---

## Features

| | |
|---|---|
| **Data source** | Robust parser over the [ScrapedDuck](https://github.com/bigfoott/ScrapedDuck) JSON feed (a structured Leek Duck mirror), plus a best-effort official-blog HTML source behind the same interface. |
| **Hybrid GUI** | Desktop (**CustomTkinter**) + Web (**Flask + Tailwind**), both *Midnight Blue* dark mode driven by **one shared palette**. |
| **i18n** | English (default), Traditional Chinese, Simplified Chinese, **Japanese, Korean** — every string lives in `languages.json`. |
| **Region filtering** | Pick the regions you care about; Global events always show. Rules live in editable `data/regions_map.json`. |
| **Search & filters** | Live search + event-type filter + **favorites** in both UIs, on top of the region filter. |
| **Rich cards & detail view** | Thumbnails, **synthesised descriptions**, live countdowns, a live/upcoming/total stats bar, and a click-through **event detail view** (desktop modal / web page). |
| **Favorites** | Star event types; filter to favorites and optionally **notify only for favorites**. |
| **Calendar export** | Per-event or filtered **.ics** export, plus a subscribable web feed at `/calendar.ics`. |
| **Notifications** | Desktop + in-app alerts, **webhooks** (Discord/Slack/custom, optionally **HMAC-signed**), and **Telegram** — when *new* events appear in your regions. |
| **Config import/export** | Back up or move your settings from either UI. |
| **Async + responsive** | `async`/`await` (httpx) fetches off the GUI thread, with a skeleton loading screen. |
| **Persistence** | **SQLite** (indexed) caches events for offline viewing; old events auto-pruned. |
| **Background updates** | **APScheduler** on a configurable interval; the web view auto-detects new events. |
| **Distribution** | **CI** (pytest matrix), a **Dockerfile** for the web app, and a one-file **Windows .exe** built on release. |
| **Graceful errors** | Network/format failures never crash the UI — cached data stays visible with a localized message. |
| **Tested** | Deterministic, offline **pytest** suite (27 tests) covering core, service, web, calendar, favorites, HMAC, and the scheduler. |

---

## Project structure

```
PokéTrack App/
├── main.py              # entry point → desktop GUI
├── run_web.py           # entry point → web GUI
├── config.json          # user settings (language, regions, interval, webhook, …)
├── languages.json       # ALL UI strings (en / zh-Hant / zh-Hans)
├── requirements.txt
├── LICENSE              # MIT (original code only)
├── DISCLAIMER.md        # trademarks, data attribution, no-warranty notice
├── data/                # SQLite DB + image cache (auto-created)
├── tests/               # offline pytest suite
└── poketrack/
    ├── app_context.py   # builds the shared service (config+db+parser+scheduler)
    ├── config.py        # config.json manager
    ├── i18n.py          # Translator (dotted keys + fallback)
    ├── core/            # data layer — NO UI imports
    │   ├── models.py    # Event model + status/countdown logic
    │   ├── regions.py   # region constants + keyword classifier
    │   ├── database.py  # SQLite persistence (thread-safe, WAL, pruning, migrations)
    │   ├── http.py      # shared requests.Session with retries/backoff
    │   ├── parser.py    # LeekDuck (JSON) + Blog (HTML) sources
    │   ├── notify.py    # optional desktop notifications (guarded)
    │   ├── webhook.py   # outgoing webhooks (Discord/Slack/generic)
    │   ├── scheduler.py # APScheduler wrapper
    │   └── service.py   # PokeTrackService — the shared controller
    ├── gui/             # desktop presentation
    │   ├── theme.py     # Midnight Blue palette — single source of truth
    │   ├── images.py    # async thumbnail loader (off-thread, cached)
    │   └── app.py       # CustomTkinter app
    └── web/             # web presentation
        ├── server.py    # Flask app + JSON API
        ├── templates/   # base.html (Tailwind config injected) + index.html
        └── static/      # css/style.css, js/app.js
```

### Architecture at a glance

```
            ┌──────────────────────────────┐
            │     PokeTrackService          │  ← the only thing both UIs touch
            │  (core/service.py)            │
            └───┬───────────┬───────────┬───┘
   parser.py    │  database │  scheduler│
 (LeekDuck/Blog)│  (SQLite) │ (APSched) │
                ▼           ▼           ▼
        ┌───────────────┐   ┌──────────────────┐
        │ gui/app.py    │   │ web/server.py    │
        │ CustomTkinter │   │ Flask + Tailwind │
        └───────────────┘   └──────────────────┘
                 ▲                   ▲
                 └──── theme.py ─────┘   (one Midnight Blue palette)
```

The fetching/parsing logic is fully separated from presentation: both
front-ends call `PokeTrackService` only, and neither imports the parser or
database directly.

---

## Setup

```bash
pip install -r requirements.txt
```

> Python 3.10+ recommended (tested on 3.13 and 3.14). `Pillow` (thumbnails) and
> `plyer` (desktop notifications) are used with graceful fallback — if either is
> missing the app still runs, just without that one feature.

> **Multiple Python installs?** Make sure you install into the *same* interpreter
> you run with. A virtual environment avoids the mix-up entirely:
> ```bash
> python -m venv .venv && .venv\Scripts\activate   # Windows
> pip install -r requirements.txt
> ```

## Run

**Desktop app**
```bash
python main.py
```

**Web app**
```bash
python run_web.py
# then open http://127.0.0.1:5000/
```

The desktop app's **“Open Web View”** button launches the web server for you and
opens your browser.

## Test

```bash
python -m pytest -q
```

The suite is fully offline (a fake source + temp DB) and won't touch your real
`config.json` or `data/`. It also runs in **CI** on every push (Python 3.11–3.13).

## Build & deploy

**Docker (web app)**
```bash
docker build -t poketrack .
docker run -p 5000:5000 poketrack      # http://localhost:5000/
```

**Standalone Windows executable**
```bash
pip install pyinstaller
pyinstaller --noconfirm PokeTrack.spec  # -> dist/PokeTrack.exe
```
On GitHub, publishing a Release triggers `.github/workflows/release.yml`, which
builds `PokeTrack.exe` and attaches it to that release automatically.

---

## Configuration — `config.json`

```jsonc
{
  "language": "en",                  // "en" | "zh-Hant" | "zh-Hans"
  "regions": ["Global"],             // see region list below
  "source": "leekduck",              // "leekduck" (default) | "blog"
  "refresh_interval_minutes": 60,    // APScheduler interval
  "notifications": true,             // desktop/in-app alerts for new events
  "webhook_url": "",                 // POST new-event alerts here (Discord/Slack/custom)
  "prune_after_days": 45,            // drop events that ended over N days ago
  "database_path": "data/poketrack.db",
  "web": { "host": "127.0.0.1", "port": 5000, "debug": false }
}
```

### Webhooks

Set `webhook_url` (in `config.json` or the desktop **Settings** tab) to receive a
POST whenever new events appear in your selected regions. The payload is shaped
automatically for the destination:

| URL contains | Format sent |
|---|---|
| `discord.com/api/webhooks/…` | Discord `{ content, embeds[] }` |
| `hooks.slack.com/…` | Slack `{ text }` |
| anything else | Generic `{ content, text, title, events[] }` |

The Settings tab has a **Send test** button to verify your URL.

Everything here is also editable in the app's **Settings** tab.

> `config.json` is **git-ignored** (it can hold a private webhook URL). A
> [`config.example.json`](config.example.json) is provided for reference; the app
> auto-creates `config.json` from defaults on first run.

---

## Internationalisation — `languages.json`

All UI text is loaded from `languages.json`, grouped by language then by section:

```json
{ "en": { "events": { "view_details": "View Details" } } }
```

Code looks strings up by dotted key with graceful fallback
(*current language → English → the key itself*):

```python
service.t("events.view_details")
service.t("events.last_updated", time="…")   # supports {placeholders}
```

**To add a language:** copy the `"en"` block to a new top-level key (e.g.
`"ja"`), translate the values, and add its display name under every
`languages` block. No code changes needed.

---

## Regions

`Global`, `North America`, `South America`, `Europe`, `Asia`, `Oceania`,
`Africa`.

Leek Duck data isn't region-tagged, so PokéTrack infers a region from the event
name using a keyword map (`core/regions.py`) — Safari Zones / GO Tour stops map
to their city/continent; everything else stays **Global** and shows for
everyone. Selecting a region (e.g. *Asia*) shows **Global + Asia**. Extend the
keyword map freely as new regional events appear.

---

## Design system — *Midnight Blue*

Deep blues, charcoal grays, and slate accents, defined once in
[`poketrack/gui/theme.py`](poketrack/gui/theme.py). The desktop UI reads the hex
values directly; the web layer injects the **same** values into its Tailwind
config and CSS variables (`web/templates/base.html`), so the two interfaces stay
identical.

| Token | Hex | Use |
|---|---|---|
| `bg` | `#0B1120` | App background |
| `surface` | `#111827` | Cards / panels |
| `surface_alt` | `#1E293B` | Elevated surfaces |
| `border` | `#334155` | Slate borders |
| `primary` | `#3B82F6` | Primary actions |
| `accent` | `#38BDF8` | Highlights |
| `text` / `text_muted` | `#E2E8F0` / `#94A3B8` | Text |
| `success` / `warning` / `danger` | `#34D399` / `#FBBF24` / `#F87171` | LIVE / SOON / errors |

---

## Notes & troubleshooting

- **First launch** shows an empty list for a second while the initial fetch
  runs in the background; it fills in automatically.
- **Offline?** Cached events from the last successful fetch remain visible and a
  localized "showing cached data" message appears.
- The default data source depends on a public community feed; if it's
  unreachable, switch `"source"` to `"blog"` in `config.json`.

---

## Credits

- **Event data:** [Leek Duck](https://leekduck.com), via the
  [ScrapedDuck](https://github.com/bigfoott/ScrapedDuck) dataset. Please support
  the original source.
- Built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter),
  [Flask](https://flask.palletsprojects.com/),
  [APScheduler](https://apscheduler.readthedocs.io/), and
  [Tailwind CSS](https://tailwindcss.com/).

## License & legal

- **Original code:** released under the [MIT License](LICENSE). The MIT grant
  covers this project's source code **only**.
- **Trademarks & third-party data:** Pokémon / Pokémon GO intellectual property
  and Leek Duck event data are **not** covered by the MIT license and remain the
  property of their respective owners. This is an unofficial, non-commercial fan
  project with **no affiliation or endorsement**, provided **"AS IS"** without
  warranty.
- Full terms: **[DISCLAIMER.md](DISCLAIMER.md)**.

> Replace the copyright holder in `LICENSE` with your name/handle before
> publishing if you'd like attribution.
