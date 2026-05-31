"""Object-graph bootstrap.

Both entry points (``main.py`` for desktop, ``run_web.py`` for web) call
:func:`build_service` so there is exactly one place that assembles config +
translator + database + service.  Paths are resolved relative to the project
root, so the app works regardless of the current working directory.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .core.database import Database
from .core.service import PokeTrackService
from .i18n import Translator

logger = logging.getLogger(__name__)

# Project root = the folder that contains this package.
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
    translator = Translator(ROOT / "languages.json", language=config.get("language", "en"))
    db_path = ROOT / config.get("database_path", "data/poketrack.db")
    database = Database(db_path)
    return PokeTrackService(config, translator, database)
