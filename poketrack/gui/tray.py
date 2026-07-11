"""Optional system-tray icon (pystray).

Gracefully disabled if pystray/Pillow aren't available — :func:`available`
returns False and the desktop app simply closes normally instead of minimizing
to the tray. Menu callbacks run on the pystray thread, so the app passes
thread-safe callbacks (they enqueue onto the Tk UI queue).
"""
from __future__ import annotations

import logging
import threading

from ..app_context import RESOURCE_ROOT
from .theme import MIDNIGHT_BLUE as C

logger = logging.getLogger(__name__)

try:
    import pystray
    from PIL import Image, ImageDraw
    _OK = True
except Exception:  # noqa: BLE001 - optional dependency
    _OK = False


def available() -> bool:
    return _OK


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    """``"#RRGGBB"`` -> an opaque ``(r, g, b, 255)`` tuple for PIL."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _icon_image():
    """The PokéTracker radar icon, or a drawn Midnight Blue dot as a fallback."""
    asset = RESOURCE_ROOT / "assets" / "icon.png"
    try:
        if asset.exists():
            return Image.open(asset)
    except Exception:  # noqa: BLE001 - fall through to the drawn fallback
        logger.debug("Could not load tray icon asset", exc_info=True)
    img = Image.new("RGBA", (64, 64), _hex_to_rgba(C["bg"]))
    draw = ImageDraw.Draw(img)
    draw.ellipse((14, 14, 50, 50), fill=_hex_to_rgba(C["accent"]))
    return img


class TrayIcon:
    def __init__(self, *, on_show, on_refresh, on_quit, title="PokéTrack",
                 labels=("Show", "Refresh", "Quit")) -> None:
        self._on_show = on_show
        self._on_refresh = on_refresh
        self._on_quit = on_quit
        self._title = title
        self._labels = labels
        self._icon = None

    def start(self) -> bool:
        if not _OK:
            return False
        show, refresh, quit_ = self._labels
        menu = pystray.Menu(
            pystray.MenuItem(show, lambda *_: self._on_show(), default=True),
            pystray.MenuItem(refresh, lambda *_: self._on_refresh()),
            pystray.MenuItem(quit_, lambda *_: self._on_quit()),
        )
        self._icon = pystray.Icon("poketrack", _icon_image(), self._title, menu)
        threading.Thread(target=self._icon.run, name="poketrack-tray", daemon=True).start()
        return True

    def stop(self) -> None:
        try:
            if self._icon is not None:
                self._icon.stop()
        except Exception:  # noqa: BLE001
            pass
