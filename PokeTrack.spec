# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the PokéTrack desktop app (one-file, windowed).

    pyinstaller --noconfirm PokeTrack.spec   ->   dist/PokeTrack.exe

Bundled read-only assets (languages.json, data/regions_map.json, CustomTkinter
theme files) are unpacked to a temp dir at runtime; the app reads them via
``RESOURCE_ROOT`` while writable files (config.json, the SQLite DB, the image
cache) live next to the executable via ``ROOT`` — see poketrack/app_context.py.
"""
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("languages.json", "."),
    ("data/regions_map.json", "data"),
]
datas += collect_data_files("customtkinter")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PokeTrack",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # windowed (no console) — it's a GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
