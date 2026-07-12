# PokéTrack Desktop (Tauri)

A native desktop shell (Rust / [Tauri](https://tauri.app)) that reuses the
**web UI** verbatim: on launch it starts the Flask app as a bundled sidecar,
waits for its port, then opens a native window pointed at it. The window *is*
the fusion web design — full CSS fidelity — with native chrome and a tiny
binary (uses the OS WebView2, not a bundled Chromium).

```
desktop/
├── src/index.html          # tiny splash (frontendDist placeholder)
└── src-tauri/
    ├── src/main.rs          # spawn sidecar → poll port → open window; Job Object cleanup
    ├── tauri.conf.json      # NSIS installer + bundles the server sidecar as a resource
    ├── Cargo.toml
    ├── icons/               # generated from ../../assets/icon.png
    └── binaries/            # poketrack-server.exe (built below; git-ignored, 40 MB)
```

## Why a sidecar

The desktop app must run **without Python installed**, so the Flask server
(`run_web.py` + all deps + templates/static + `languages.json` + the Rust
extension) is frozen into a single `poketrack-server.exe` with PyInstaller and
bundled into the Tauri app as a resource. `main.rs` prefers that bundled binary
and falls back to `python run_web.py` in dev. When frozen, the server writes
config/DB/cache to a per-user dir (`%APPDATA%\PokeTrack`), never the (read-only)
install dir — see `poketrack/app_context.py`.

The server is assigned to a Windows **Job Object** (`KILL_ON_JOB_CLOSE`) so it
can never orphan: it dies with the app on clean quit, crash, or a Task-Manager
kill.

## Build

Prerequisites: Rust, Node, Python (with the project deps + `pyinstaller`), and a
WebView2 runtime (preinstalled on Windows 11).

```bash
# 1. Build the server sidecar (from the repo root)
pyinstaller --noconfirm --distpath dist-server --workpath build-server PokeTrack-server.spec
cp dist-server/poketrack-server.exe desktop/src-tauri/binaries/poketrack-server.exe

# 2. Build the installer
cd desktop
npm install
npm run build            # -> src-tauri/target/release/bundle/nsis/PokeTrack_<ver>_x64-setup.exe
```

`npm run dev` runs the shell in dev mode (falls back to `python run_web.py`, so
no sidecar build is needed to iterate).

## Status

POC / early — proven end-to-end: the NSIS installer installs per-user, launches,
spawns the bundled sidecar, and renders the fusion UI with live data, no Python
required. Native tray/notifications (currently in the Python/web layer) are a
candidate to move to Tauri's native APIs. CI to build + attach the installer on
release is a planned follow-up.
