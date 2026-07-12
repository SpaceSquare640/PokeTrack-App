"""Object-graph bootstrap.

Both entry points (``main.py`` for desktop, ``run_web.py`` for web) call
:func:`build_service` so there is exactly one place that assembles config +
translator + database + service.  Paths are resolved relative to the project
root, so the app works regardless of the current working directory.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .config import Config
from .core.database import Database
from .core.service import PokeTrackService
from .i18n import Translator

logger = logging.getLogger(__name__)

_FROZEN = getattr(sys, "frozen", False)

# RESOURCE_ROOT — read-only bundled assets (languages.json, region map). When
# frozen by PyInstaller these live in the unpacked temp dir (_MEIPASS).
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", "")) if _FROZEN else Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    """Per-user writable data dir (used when installed, e.g. under Program Files)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "PokeTrack"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PokeTrack"
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "PokeTrack"


# ROOT — writable location for config.json, the SQLite DB and the image cache.
# A per-user data dir when frozen (the install dir may be read-only, e.g. Program
# Files); the project root when running from source.
if _FROZEN:
    ROOT = _user_data_dir()
    ROOT.mkdir(parents=True, exist_ok=True)
else:
    ROOT = Path(__file__).resolve().parent.parent


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_service() -> PokeTrackService:
    """Construct a fully wired :class:`PokeTrackService`."""
    config = Config(ROOT / "config.json")
    # languages.json is a bundled asset → RESOURCE_ROOT; the DB is writable → ROOT.
    translator = Translator(RESOURCE_ROOT / "languages.json", language=config.get("language", "en"))
    db_path = ROOT / config.get("database_path", "data/poketrack.db")
    database = Database(db_path)
    return PokeTrackService(config, translator, database)
