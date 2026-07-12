# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the PokéTrack web server, bundled as a Tauri sidecar.

    pyinstaller --noconfirm PokeTrack-server.spec   ->   dist/poketrack-server.exe

A single, self-contained executable that runs the Flask app (run_web.py) with
Python, all deps, the templates/static assets, languages.json, the region map,
and the optional Rust extension baked in. The Tauri desktop shell spawns this on
launch and points a native window at it. Writable data (config.json, the SQLite
DB, image cache) is redirected to a per-user dir by app_context (the install dir
may be read-only), so nothing is written next to this executable.
"""
from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("languages.json", "."),
    ("data/regions_map.json", "data"),
    # Flask resolves templates/static relative to the poketrack/web package, so
    # they must keep that layout inside the bundle.
    ("poketrack/web/templates", "poketrack/web/templates"),
    ("poketrack/web/static", "poketrack/web/static"),
]

hiddenimports = [
    "poketrack_native",              # optional Rust fast path (guarded import)
    *collect_submodules("apscheduler"),
]

a = Analysis(
    ["run_web.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The server never touches the desktop GUI stack — keep it out of the bundle.
    excludes=["customtkinter", "tkinter", "PIL.ImageTk", "pystray", "plyer"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="poketrack-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # background sidecar — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
