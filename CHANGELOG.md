# Changelog

All notable changes to PokéTrack are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [1.8.0] — 2026-07-12 — Native desktop shell (Tauri)

Rebuilt the desktop app as a native Rust/Tauri shell, replacing the
CustomTkinter ceiling that couldn't render the fusion redesign's glassmorphism,
gradients, and animation. The new shell reuses the web UI verbatim — full CSS
fidelity, native window chrome, a tiny binary via the OS WebView2 (no bundled
Chromium) — with zero rewrite of the Python business logic.

### Added
- **`desktop/` (Tauri, Rust).** On launch: spawn the Flask app as a bundled
  sidecar, poll its port, then open a native window pointed at it. The window
  *is* the fusion design (dual theme, hero, KPI cards, glass cards — all of it).
- **`PokeTrack-server.spec`** freezes `run_web.py` (+ deps, templates/static,
  `languages.json`, the region map, the optional Rust extension) into a single
  `poketrack-server.exe`, bundled into the installer as a resource — installing
  the app needs **no Python**.
- **Per-user data dir when frozen** (`app_context.py`): writable data
  (config/DB/image cache) now goes to `%APPDATA%/PokeTrack` instead of next to
  the executable, since the install directory may be read-only.
- **Windows Job Object** (`KILL_ON_JOB_CLOSE`) ties the sidecar's lifetime to
  the app so it can never orphan — verified the server exits with the app even
  on a hard kill, releasing its port immediately.
- **NSIS installer** (`PokeTrack_<version>_x64-setup.exe`), per-user install,
  no admin rights required.

### Notes
- Verified end-to-end from a real install: installs to `%LOCALAPPDATA%\PokeTrack`,
  launches, spawns the bundled sidecar, renders the fusion UI with live data.
- The prior CustomTkinter desktop app (`main.py`, `poketrack/gui/`) is
  unchanged and still ships as `PokeTrack.exe` for this release; the Tauri
  shell is the new one going forward. 31 tests pass.
- CI to build and attach the installer automatically on release is a planned
  follow-up — this release's installer was built locally.

## [1.7.0] — 2026-07-12 — Fusion redesign

A full GUI/UI redesign for both interfaces, converged from four explored
directions (modern dashboard, playful/vibrant, minimalist editorial, dual
light/dark) into one "fusion" design, prototyped as static mockups
(`poketrack/web/static/mockups/`) before implementation.

### Added
- **Dual theme (light/dark), both UIs.** A new `PAPER_LIGHT` palette in
  `theme.py` (same keys as `MIDNIGHT_BLUE`). Web ships both as CSS variables
  and toggles client-side (persisted via `localStorage`, applied before first
  paint — no flash). Desktop reads a mutable `theme.ACTIVE` palette; switching
  in Settings rebuilds the UI in place and persists to `config.json`.
- **Dashboard layout.** Persistent sidebar (web) / KPI stat cards (both UIs):
  live / upcoming / total / favorite-type counts, with sparkline accents on
  web.
- **Live hero banner** — a brand-colored, clickable spotlight for the
  headline active event with a live countdown, shown on the default
  unfiltered view.
- **Date-grouped sections** (web) — live first, then upcoming grouped by
  start date, then past events (most recent first); instant search now also
  collapses emptied date-group headers.
- **Status filter chips** (web) — all/live/upcoming/ended/favorites as
  server-linked pills alongside the existing search/type filters.
- Serif display typography for headings on both UIs (editorial-influenced).
- Mockups (`poketrack/web/static/mockups/`) kept in the repo as design
  references for future iteration.

### Changed
- Status colours (badges, countdowns) now resolve against the active theme
  instead of a hardcoded dark-mode hex, so they're correct in both themes.

### Notes
- No functional/data changes. 31 tests pass. Verified in-browser (both
  themes round-trip, 0 unnamed interactive controls, no console errors) and
  via headless desktop construction (hero + KPI + light/dark rebuild).

## [1.6.0] — 2026-07-12 — Update check & community links

### Added
- **Automatic update check** — a best-effort GitHub-releases check runs at
  startup and every 6 hours (`poketrack/core/updates.py`, reusing the shared
  retrying HTTP session; fail-silent). When a newer release exists, the desktop
  shows a clickable footer badge and the web shows a top banner, both opening
  the release page. Nothing shows when up to date.
- **Footer with community links** — a persistent bottom bar in both UIs with
  links to the maintainer's GitHub profile and Discord community (icons
  bundled for the desktop `.exe`, served static for the web) plus a credit line.

### i18n
- New `update.available` + `footer.*` strings across all 5 languages.

### Notes
- 31 tests pass. Update logic verified against the live GitHub API; the desktop
  UI (footer + badge) verified via headless construction.

## [1.5.1] — 2026-07-11 — Accessibility & polish pass

Applied third-party UI skills (ibelick's baseline-ui/fixing-accessibility/
fixing-metadata/fixing-motion-performance rule sets) to both interfaces —
polish only, no behavior/feature changes.

### Web
- Accessible names on every select/icon-only control; `aria-pressed` on
  favorite toggles (synced live from TS); toast is now a `role="status"`
  live region; decorative glyphs marked `aria-hidden`.
- `tabular-nums` on stats/countdowns/dates; `text-balance` on headings,
  `text-pretty` on body copy; empty state now offers a "Clear filters"
  next action.
- `prefers-reduced-motion` respected; `min-h-screen` → `min-h-dvh`
  (mobile-safe); Open Graph/Twitter meta tags added.
- **Contrast fix (both UIs):** the shared `text_faint` palette color failed
  WCAG AA for small text (3.07–3.96:1) — lightened to `#8091A8`
  (4.55–5.86:1) in the single palette source both interfaces read.

### Desktop
- Every hardcoded white text color replaced with a new `on_primary` theme
  token; the tray's fallback icon now derives its colors from the shared
  palette instead of duplicating hex literals.
- Fixed the one untranslated string in the app (tray's "Quit") — new
  `nav.quit` key across all 5 languages.
- Calendar-export button gets a text label (was icon-only); empty state
  gets a "Clear filters" action when a filter is active.
- Keyboard: Escape/window-close now dismiss the event detail modal; Enter
  saves settings from any text field.
- Minor spacing/sizing parity fixes (button heights, skeleton-to-card
  padding) to remove a small layout jump.

### Notes
- 31 tests pass. Verified via real runtime construction and simulated
  keyboard events (not just static analysis) — see commit messages for
  the full verification trail.

## [1.5.0] — 2026-07-11 — Reminders, history, PWA, shiny bosses

### Added
- **Event reminders** — a desktop/webhook/Telegram alert fires once, N minutes
  before an event starts (`remind_before_minutes`, default 15, `0` = off).
  Configurable in both the web and desktop Settings. Runs off a 1-minute
  scheduler check independent of the fetch interval; honours the region filter
  and notify-favorites-only.
- **Past-events / status filter** — the web dashboard gains an
  All / Live / Upcoming / Ended filter (surfacing the store's existing
  status-aware queries), threaded through the page, `/api/events`, and
  `/calendar.ics`.
- **Progressive Web App** — the web app is now installable and works offline: a
  `manifest.webmanifest` (reusing the icon set) and a network-first service
  worker that caches the app shell + last-seen data. Running still needs no
  Node; it's a progressive enhancement.
- **Shiny raid bosses** — bosses that can be shiny are marked with ✨ (from the
  feed's `canBeShiny`), in both the Python and Rust parsers.

### Notes
- No breaking changes. 31 tests pass. Shareable filter links already work via
  the URL's query parameters (search/type/status/favorites).

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

[1.8.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.8.0
[1.7.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.7.0
[1.6.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.6.0
[1.5.1]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.5.1
[1.5.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.5.0
[1.4.1]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.4.1
[1.4.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.4.0
[1.3.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.3.0
[1.2.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.2.0
[1.0.0]: https://github.com/SpaceSquare640/PokeTrack-App/releases/tag/v1.0.0
