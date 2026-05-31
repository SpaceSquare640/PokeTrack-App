"""Launch the PokéTrack desktop application (CustomTkinter).

    python main.py

Starts the background scheduler + an immediate fetch, then opens the window.
"""
from __future__ import annotations

import logging
import sys

from poketrack.app_context import build_service, configure_logging


def main() -> int:
    configure_logging()
    log = logging.getLogger("poketrack.main")

    service = build_service()

    # Import the GUI lazily so a missing CustomTkinter gives a friendly message
    # instead of a stack trace on import.
    try:
        from poketrack.gui.app import PokeTrackApp
    except ImportError as exc:
        log.error("CustomTkinter is required for the desktop UI: %s", exc)
        print("\n  Install dependencies first:\n      pip install -r requirements.txt\n")
        return 1

    app = PokeTrackApp(service)
    service.start(refresh_now=True)  # scheduler + first fetch (off the UI thread)
    try:
        app.mainloop()
    finally:
        service.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
