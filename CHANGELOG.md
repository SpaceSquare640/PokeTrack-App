# Changelog

All notable changes to PokéTrack are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [1.4.1] — 2026-07-11 — Icon update

### Added
- A real app icon (the "PokéTracker" radar mark) replacing the unbranded
  defaults, wired into every surface:
  - `assets/icon.ico` (multi-resolution) embedded into `PokeTrack.exe` via
    PyInstaller.
  - Desktop window/taskbar icon (`iconbitmap`, with a Pillow `iconphoto`
    fallback) — best-effort, never blocks startup.
  - System-tray icon (`poketrack/gui/tray.py`) now uses the real asset instead
    of a code-drawn placeholder dot.
  - Web favicon set (`favicon.ico` + 16/32/180/192/512 PNGs) linked from
    `base.html` for browser tabs and "add to home screen".

### Notes
- No functional/behavioral changes; purely branding. 30 tests pass.

## [1.4.0] — 2026-07-11 — Polyglot

PokéTrack becomes a **polyglot** application: each language does what it does
best, with graceful fallback so nothing is a hard requirement.

### Added — Rust native fast path (`poketrack-native/`)
- A **Rust + PyO3** extension that parses the ScrapedDuck feed and classifies
  regions in native code (`parse_feed`, `classify_region`).
- Built as an **abi3 wheel** (`cp39-abi3`) — one wheel works on any CPython ≥ 3.9
  (incl. 3.13 and 3.14), so it needn't be rebuilt per interpreter.
- Loaded via `poketrack/core/native.py`, which **falls back to pure Python** when
  the extension isn't installed — the app and the full test suite behave
  identically either way (verified by a native/Python parity test).
- `benchmark.py` compares both paths honestly: the native JSON→structured-data
  step is ~3–5× faster; end-to-end the gain is smaller because building Python
  `Event` objects dominates.
- CI builds and tests with the extension; `release.yml` bundles it into
  `PokeTrack.exe` and attaches the wheel to the release.

### Added — TypeScript web front-end (`web-frontend/`)
- The web interactive layer is now **TypeScript**, compiled by **Vite** to a
  single committed bundle (`poketrack/web/static/dist/app.js`) — running the app
  still needs **no Node**; only rebuilding does.
- Progressive enhancement over the Flask server-rendered page (works with JS off):
  - **Live countdown timers** that tick every second and flip upcoming→active,
    localized from the same `languages.json` templates.
  - **Instant client-side search** that filters cards as you type.
  - **No-reload favorite toggling** via a new `POST /api/favorite` JSON endpoint.
  - Async refresh + non-intrusive new-events poller (ported to typed code).
- CI type-checks and builds the front-end on every push.

### Notes
- No breaking changes. Both additions are optional and degrade gracefully.
- Remaining roadmap items (event reminders, boss/reward detail, history stats,
  cross-platform packaging, auto-changelog, feed cache validation) are queued
  for a future release.

## [1.3.0] — Distribution, calendar, polish, reach
- CI (pytest matrix), Windows `.exe`, and a Dockerfile for the web app.
- Calendar (`.ics`) export + favorites.
- Timezone/time-format options, event detail view, system-tray minimise.
- Japanese + Korean translations; Telegram alerts.

## [1.2.0]
- Region map JSON, async fetches, config import/export, DB name index,
  skeleton loading, webhook HMAC signing, expanded tests.

## [1.0.0] — Initial release
- Hybrid CustomTkinter desktop + Flask web UI sharing one Midnight Blue theme.
- ScrapedDuck (Leek Duck) source, SQLite persistence, APScheduler updates,
  i18n (English / Traditional Chinese / Simplified Chinese), region filtering.

[1.4.1]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.4.1
[1.4.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.4.0
[1.3.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.3.0
[1.2.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.2.0
[1.0.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.0.0
