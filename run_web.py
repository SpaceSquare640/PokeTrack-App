"""Launch the PokéTrack web application (Flask).

    python run_web.py

Then open http://127.0.0.1:5000/ (host/port configurable in config.json).
"""
from __future__ import annotations

import os

from poketrack.app_context import build_service, configure_logging
from poketrack.web.server import create_app


def main() -> int:
    configure_logging()
    service = build_service()
    service.start(refresh_now=True)  # scheduler + first fetch in the background

    app = create_app(service)
    # Env vars take precedence over config.json (used by the Docker image).
    host = os.environ.get("POKETRACK_WEB_HOST") or service.config.get("web.host", "127.0.0.1")
    port = int(os.environ.get("POKETRACK_WEB_PORT") or service.config.get("web.port", 5000))
    debug = bool(service.config.get("web.debug", False))

    try:
        # use_reloader=False: the reloader would spawn a second process and start
        # the scheduler/fetch twice.
        app.run(host=host, port=port, debug=debug, use_reloader=False)
    finally:
        service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
