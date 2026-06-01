"""The PokéTrack desktop application (CustomTkinter, Midnight Blue dark theme).

UI principles enforced here:

* **Every visible string** comes from the translator (``self.t(...)``) — nothing
  is hard-coded, so switching language re-renders the whole window from
  ``languages.json``.
* **Every colour** comes from the shared :data:`MIDNIGHT_BLUE` palette, so the
  desktop UI matches the web UI exactly.
* **Threading is safe.** Network fetches and image downloads run on worker
  threads and hand results back through a queue the Tk main loop drains — no Tk
  object is ever created or touched off the main thread.

Features: search + event-type filter, region filter, live status stats,
countdown timers, event thumbnails (async, cached), and new-event alerts.
"""
from __future__ import annotations

import logging
import queue
import subprocess
import sys
import threading
import webbrowser
from tkinter import filedialog

import customtkinter as ctk

from ..app_context import ROOT
from ..core.asyncrunner import RUNNER
from ..core.regions import REGIONS
from ..core.service import PokeTrackService, RefreshResult
from . import tray as tray_mod
from .images import ImageLoader
from .theme import FONT_FAMILY, MIDNIGHT_BLUE as C, status_color

logger = logging.getLogger(__name__)

SIDEBAR_WIDTH = 240
IMAGE_SIZE = (104, 104)


class PokeTrackApp(ctk.CTk):
    def __init__(self, service: PokeTrackService) -> None:
        super().__init__()
        self.service = service
        self._current_view = "events"
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._region_vars: dict[str, ctk.BooleanVar] = {}
        self._ui_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()

        # Filter state (preserved across language re-renders).
        self._search_text: str = ""
        self._type_filter: str | None = None       # raw event_type, or None = all
        self._favorites_only: bool = False
        self._search_job: str | None = None         # debounce handle
        self._web_proc: subprocess.Popen | None = None
        self._tray = None                            # lazily-created system tray icon
        # True until the first fetch resolves — drives the skeleton loading state.
        self._loading: bool = self.service.last_updated() is None

        # Image cache: url -> CTkImage (created on the main thread). Pending maps
        # url -> labels awaiting that image; rebuilt every render.
        self._img_cache: dict[str, ctk.CTkImage] = {}
        self._img_pending: dict[str, list[ctk.CTkLabel]] = {}
        self._image_loader = ImageLoader(
            cache_dir=ROOT / "data" / "img_cache",
            on_ready=self._on_image_ready,
            size=IMAGE_SIZE,
        )

        # Background refreshes/images push onto our queue; the main loop drains it.
        self.service.on_update = lambda result: self._ui_queue.put(("background", result))

        # --- appearance ---
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")
        self.title(self.t("app.title"))
        self.geometry("1100x720")
        self.minsize(920, 580)
        self.configure(fg_color=C["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Fonts (created after the Tk root exists).
        self.font_title = ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold")
        self.font_subtitle = ctk.CTkFont(family=FONT_FAMILY, size=12)
        self.font_section = ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold")
        self.font_card_title = ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        self.font_body = ctk.CTkFont(family=FONT_FAMILY, size=12)
        self.font_small = ctk.CTkFont(family=FONT_FAMILY, size=11)
        self.font_badge = ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold")

        self._build_ui()
        self.after(200, self._poll_queue)
        self.after(60_000, self._tick)

    # ------------------------------------------------------------------ #
    # Small helpers                                                      #
    # ------------------------------------------------------------------ #
    def t(self, key: str, **kwargs) -> str:
        return self.service.t(key, **kwargs)

    # ------------------------------------------------------------------ #
    # UI construction                                                    #
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """(Re)build the entire window. Called on first run and on language change."""
        if hasattr(self, "container"):
            self.container.destroy()

        self.container = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.container.pack(fill="both", expand=True)
        self.container.grid_columnconfigure(1, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self.content = ctk.CTkFrame(self.container, fg_color=C["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        self._show_view(self._current_view)

    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(
            self.container, width=SIDEBAR_WIDTH, fg_color=C["bg_alt"], corner_radius=0
        )
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(
            bar, text=self.t("app.title"), font=self.font_title, text_color=C["accent"]
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(22, 0))
        ctk.CTkLabel(
            bar, text=self.t("app.subtitle"), font=self.font_subtitle,
            text_color=C["text_muted"], wraplength=SIDEBAR_WIDTH - 40, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(2, 18))

        self._nav_buttons = {}
        for i, (view, key) in enumerate([("events", "nav.events"), ("settings", "nav.settings")]):
            btn = ctk.CTkButton(
                bar, text=self.t(key), anchor="w", height=40, corner_radius=8,
                font=self.font_body, command=lambda v=view: self._show_view(v),
                fg_color="transparent", hover_color=C["surface_alt"], text_color=C["text"],
            )
            btn.grid(row=2 + i, column=0, sticky="ew", padx=14, pady=3)
            self._nav_buttons[view] = btn

        self.refresh_btn = ctk.CTkButton(
            bar, text=self.t("nav.refresh"), height=40, corner_radius=8, font=self.font_body,
            fg_color=C["primary"], hover_color=C["primary_hover"], text_color="#FFFFFF",
            command=self._on_refresh,
        )
        self.refresh_btn.grid(row=4, column=0, sticky="ew", padx=14, pady=(16, 3))

        ctk.CTkButton(
            bar, text=self.t("nav.open_web"), height=40, corner_radius=8, font=self.font_body,
            fg_color="transparent", hover_color=C["surface_alt"], text_color=C["text"],
            border_width=1, border_color=C["border"], command=self._open_web,
        ).grid(row=5, column=0, sticky="ew", padx=14, pady=3)

        self.status_label = ctk.CTkLabel(
            bar, text=self.t("status.ready"), font=self.font_small,
            text_color=C["text_muted"], wraplength=SIDEBAR_WIDTH - 36, justify="left",
        )
        self.status_label.grid(row=7, column=0, sticky="sw", padx=20, pady=16)

        self._highlight_nav()

    def _highlight_nav(self) -> None:
        for view, btn in self._nav_buttons.items():
            active = view == self._current_view
            btn.configure(
                fg_color=C["surface_alt"] if active else "transparent",
                text_color=C["accent"] if active else C["text"],
            )

    # ------------------------------------------------------------------ #
    # View switching                                                     #
    # ------------------------------------------------------------------ #
    def _show_view(self, view: str) -> None:
        self._current_view = view
        self._highlight_nav()
        for child in self.content.winfo_children():
            child.destroy()
        if view == "settings":
            self._build_settings_view()
        else:
            self._build_events_view()

    # ------------------------------------------------------------------ #
    # Events view                                                        #
    # ------------------------------------------------------------------ #
    def _build_events_view(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color=C["bg"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 6))
        header.grid_columnconfigure(0, weight=1)

        # Row 0: title + live stats + last-updated
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            title_row, text=self.t("events.section_all"), font=self.font_title, text_color=C["text"]
        ).grid(row=0, column=0, sticky="w")

        stats = ctk.CTkFrame(title_row, fg_color="transparent")
        stats.grid(row=0, column=1, sticky="w", padx=14)
        self.stat_live = ctk.CTkLabel(stats, text="", font=self.font_small, text_color=C["success"])
        self.stat_live.grid(row=0, column=0, padx=(0, 12))
        self.stat_upcoming = ctk.CTkLabel(stats, text="", font=self.font_small, text_color=C["warning"])
        self.stat_upcoming.grid(row=0, column=1, padx=(0, 12))
        self.stat_total = ctk.CTkLabel(stats, text="", font=self.font_small, text_color=C["text_muted"])
        self.stat_total.grid(row=0, column=2)

        self.updated_label = ctk.CTkLabel(
            title_row, text="", font=self.font_small, text_color=C["text_faint"]
        )
        self.updated_label.grid(row=0, column=2, sticky="e")

        # Row 1: search box + type filter
        tools = ctk.CTkFrame(header, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        tools.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            tools, placeholder_text=self.t("events.search_placeholder"), font=self.font_body,
            height=36, fg_color=C["surface"], border_color=C["border"], text_color=C["text"],
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        if self._search_text:
            self.search_entry.insert(0, self._search_text)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        type_values = [self.t("events.all_types")] + [
            self._type_display(tp) for tp in self.service.available_types()
        ]
        self.type_menu = ctk.CTkOptionMenu(
            tools, values=type_values, command=self._on_type_change, width=190, height=36,
            font=self.font_body, fg_color=C["surface"], button_color=C["surface_alt"],
            button_hover_color=C["border"], text_color=C["text"],
            dropdown_fg_color=C["surface_alt"], dropdown_hover_color=C["border"],
            dropdown_text_color=C["text"],
        )
        self.type_menu.grid(row=0, column=1, sticky="e")
        current = self._type_display(self._type_filter) if self._type_filter else self.t("events.all_types")
        self.type_menu.set(current)

        self.fav_btn = ctk.CTkButton(
            tools, text="★ " + self.t("events.favorites"), height=36, width=120, corner_radius=8,
            font=self.font_small, command=self._on_toggle_favorites, hover_color=C["border"],
            fg_color=C["primary"] if self._favorites_only else C["surface_alt"],
            text_color="#FFFFFF" if self._favorites_only else C["text"],
        )
        self.fav_btn.grid(row=0, column=2, sticky="e", padx=(10, 0))
        ctk.CTkButton(
            tools, text="📅", height=36, width=44, corner_radius=8, font=self.font_body,
            command=self._on_export_calendar, fg_color=C["surface_alt"], hover_color=C["border"],
            text_color=C["text"],
        ).grid(row=0, column=3, sticky="e", padx=(8, 0))

        # Scroll area
        self.events_scroll = ctk.CTkScrollableFrame(
            self.content, fg_color="transparent",
            scrollbar_button_color=C["surface_alt"], scrollbar_button_hover_color=C["border"],
        )
        self.events_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(2, 16))
        self.events_scroll.grid_columnconfigure(0, weight=1)

        self._render_events()

    def _render_events(self) -> None:
        """Populate the scroll area, grouped Active / Upcoming / Other."""
        if not hasattr(self, "events_scroll") or not self.events_scroll.winfo_exists():
            return
        for child in self.events_scroll.winfo_children():
            child.destroy()
        self._img_pending = {}  # old labels are gone; drop stale references

        events = self.service.get_events(
            search=self._search_text or None,
            event_types=[self._type_filter] if self._type_filter else None,
            favorites_only=self._favorites_only,
        )
        self._update_header_metrics(events)

        if not events:
            # Show a skeleton while the first fetch is still running; only fall
            # back to the "empty" message once we actually have a result.
            if self._loading and not self._search_text and not self._type_filter:
                self._render_skeleton()
            else:
                ctk.CTkLabel(
                    self.events_scroll, text=self.t("events.empty"),
                    font=self.font_body, text_color=C["text_muted"],
                ).grid(row=0, column=0, sticky="w", padx=8, pady=24)
            return

        buckets: dict[str, list] = {"active": [], "upcoming": [], "other": []}
        for event in events:
            st = event.status()
            buckets["active" if st == "active" else "upcoming" if st == "upcoming" else "other"].append(event)

        row = 0
        for bucket, title_key in [
            ("active", "events.section_active"),
            ("upcoming", "events.section_upcoming"),
            ("other", "events.section_other"),
        ]:
            items = buckets[bucket]
            if not items:
                continue
            ctk.CTkLabel(
                self.events_scroll, text=self.t(title_key), font=self.font_section,
                text_color=C["text_muted"],
            ).grid(row=row, column=0, sticky="w", padx=8, pady=(14, 4))
            row += 1
            for event in items:
                self._build_event_card(event, row)
                row += 1

    def _render_skeleton(self, count: int = 6) -> None:
        """Placeholder cards shown during the initial fetch (no flash of empty)."""
        for row in range(count):
            card = ctk.CTkFrame(
                self.events_scroll, fg_color=C["surface"], corner_radius=12,
                border_width=1, border_color=C["border"],
            )
            card.grid(row=row, column=0, sticky="ew", padx=6, pady=5)
            card.grid_columnconfigure(1, weight=1)
            # Thumbnail placeholder
            ctk.CTkFrame(card, fg_color=C["surface_alt"], width=IMAGE_SIZE[0] + 8,
                         height=IMAGE_SIZE[1] + 8, corner_radius=8).grid(
                row=0, column=0, rowspan=3, padx=(12, 0), pady=12)
            # Text line placeholders of varying widths
            for r, width in ((0, 150), (1, 360), (2, 240)):
                ctk.CTkFrame(card, fg_color=C["surface_alt"], width=width, height=12,
                             corner_radius=6).grid(row=r, column=1, sticky="w", padx=16,
                                                   pady=(14 if r == 0 else 6, 6))

    def _build_event_card(self, event, row: int) -> None:
        status = event.status()
        card = ctk.CTkFrame(
            self.events_scroll, fg_color=C["surface"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        card.grid(row=row, column=0, sticky="ew", padx=6, pady=5)

        content_col = 0
        # Thumbnail (left), loaded asynchronously.
        if event.image and self._image_loader.enabled:
            holder = ctk.CTkFrame(card, fg_color=C["surface_alt"], width=IMAGE_SIZE[0] + 8,
                                  height=IMAGE_SIZE[1] + 8, corner_radius=8)
            holder.grid(row=0, column=0, padx=(12, 0), pady=12)
            holder.grid_propagate(False)
            img_label = ctk.CTkLabel(holder, text="", fg_color="transparent")
            img_label.place(relx=0.5, rely=0.5, anchor="center")
            cached = self._img_cache.get(event.image)
            if cached is not None:
                img_label.configure(image=cached)
            else:
                self._img_pending.setdefault(event.image, []).append(img_label)
                self._image_loader.request(event.image)
            content_col = 1

        card.grid_columnconfigure(content_col, weight=1)
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.grid(row=0, column=content_col, sticky="nsew", padx=14, pady=10)
        content.grid_columnconfigure(0, weight=1)

        # Top row: badge + type + countdown
        top = ctk.CTkFrame(content, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(3, weight=1)
        col = 0
        badge_key = {"active": "events.active_badge", "upcoming": "events.upcoming_badge",
                     "ended": "events.ended_badge"}.get(status)
        if badge_key:
            ctk.CTkLabel(
                top, text=f"  {self.t(badge_key)}  ", font=self.font_badge,
                fg_color=C["surface_alt"], text_color=status_color(status), corner_radius=6,
            ).grid(row=0, column=col, sticky="w"); col += 1
        if event.type_label:
            ctk.CTkLabel(top, text=event.type_label, font=self.font_small,
                         text_color=C["text_faint"]).grid(row=0, column=col, sticky="w", padx=(8, 0)); col += 1
        countdown = self.service.countdown(event)
        if countdown:
            ctk.CTkLabel(top, text=countdown, font=self.font_small,
                         text_color=status_color(status)).grid(row=0, column=col + 1, sticky="e")

        ctk.CTkLabel(
            content, text=event.name, font=self.font_card_title, text_color=C["text"],
            wraplength=560, justify="left", anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 4))

        region_label = self.t(f"regions.{event.region}")
        meta = (
            f"{self.t('events.region')}: {region_label}    "
            f"{self.t('events.starts')}: {self.service.format_time(event.start)}    "
            f"{self.t('events.ends')}: {self.service.format_time(event.end)}"
        )
        ctk.CTkLabel(
            content, text=meta, font=self.font_small, text_color=C["text_muted"],
            wraplength=560, justify="left", anchor="w",
        ).grid(row=2, column=0, sticky="ew", pady=(0, 6))

        # Localized description (synthesised from heading + highlights).
        desc = self.service.description(event)
        if desc:
            if len(desc) > 170:
                desc = desc[:167].rstrip() + "…"
            ctk.CTkLabel(
                content, text=desc, font=self.font_small, text_color=C["text"],
                wraplength=560, justify="left", anchor="w",
            ).grid(row=3, column=0, sticky="ew", pady=(0, 6))

        ctk.CTkLabel(
            content, text=self.t("events.view_details") + "  →", font=self.font_small,
            text_color=C["accent"], anchor="w",
        ).grid(row=4, column=0, sticky="w", pady=(0, 2))

        # Favorite star (overlay, top-right) — excluded from the card click.
        fav_on = self.service.is_favorite(event.event_type)
        star = ctk.CTkButton(
            card, text="★" if fav_on else "☆", width=30, height=30, corner_radius=15,
            font=self.font_body, fg_color=C["surface_alt"], hover_color=C["border"],
            text_color=C["warning"] if fav_on else C["text_muted"],
            command=lambda t=event.event_type: self._toggle_favorite(t),
        )
        star.place(relx=1.0, x=-10, y=10, anchor="ne")

        # Whole card opens the in-app detail view.
        self._bind_click(card, lambda e=event: self._open_detail(e), exclude=[star])

    def _bind_click(self, root_widget, callback, exclude=()) -> None:
        """Bind left-click on a widget + all descendants to ``callback``.

        Widgets in ``exclude`` keep their own handlers (e.g. the favorite star).
        """
        excluded = set(exclude)

        def handler(_event=None):
            callback()

        stack = [root_widget]
        while stack:
            widget = stack.pop()
            if widget in excluded:
                continue
            try:
                widget.bind("<Button-1>", handler)
                widget.configure(cursor="hand2")
            except Exception:  # noqa: BLE001 - not all widgets accept cursor/binds
                pass
            try:
                stack.extend(widget.winfo_children())
            except Exception:  # noqa: BLE001
                pass

    def _toggle_favorite(self, event_type: str) -> None:
        self.service.toggle_favorite(event_type)
        self._render_events()

    def _open_detail(self, event) -> None:
        """In-app detail window for an event (Midnight Blue, localized)."""
        win = ctk.CTkToplevel(self)
        win.title(event.name)
        win.geometry("560x640")
        win.configure(fg_color=C["bg"])
        win.transient(self)
        try:
            win.after(50, win.lift)
        except Exception:  # noqa: BLE001
            pass

        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.grid_columnconfigure(0, weight=1)

        status = event.status()
        badge_key = {"active": "events.active_badge", "upcoming": "events.upcoming_badge",
                     "ended": "events.ended_badge"}.get(status)
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.grid(row=0, column=0, sticky="w")
        if badge_key:
            ctk.CTkLabel(top, text=f"  {self.t(badge_key)}  ", font=self.font_badge,
                         fg_color=C["surface_alt"], text_color=status_color(status),
                         corner_radius=6).grid(row=0, column=0, padx=(0, 8))
        cd = self.service.countdown(event)
        if cd:
            ctk.CTkLabel(top, text=cd, font=self.font_small, text_color=status_color(status)).grid(row=0, column=1)

        ctk.CTkLabel(body, text=event.name, font=self.font_title, text_color=C["text"],
                     wraplength=500, justify="left", anchor="w").grid(row=1, column=0, sticky="ew", pady=(10, 6))

        desc = self.service.description(event)
        if desc:
            ctk.CTkLabel(body, text=desc, font=self.font_body, text_color=C["text_muted"],
                         wraplength=500, justify="left", anchor="w").grid(row=2, column=0, sticky="ew", pady=(0, 10))

        meta = (
            f"{self.t('events.region')}: {self.t('regions.' + event.region)}\n"
            f"{self.t('events.type')}: {event.type_label or '—'}\n"
            f"{self.t('events.starts')}: {self.service.format_time(event.start)}\n"
            f"{self.t('events.ends')}: {self.service.format_time(event.end)}"
        )
        ctk.CTkLabel(body, text=meta, font=self.font_small, text_color=C["text"],
                     justify="left", anchor="w").grid(row=3, column=0, sticky="w", pady=(0, 10))

        if event.bosses:
            ctk.CTkLabel(body, text=self.t("desc.featured_raids", names=", ".join(event.bosses)),
                         font=self.font_small, text_color=C["text_muted"], wraplength=500,
                         justify="left", anchor="w").grid(row=4, column=0, sticky="w", pady=(0, 6))
        if event.promocodes:
            ctk.CTkLabel(body, text=self.t("desc.promo", codes=", ".join(event.promocodes)),
                         font=self.font_small, text_color=C["text_muted"], wraplength=500,
                         justify="left", anchor="w").grid(row=5, column=0, sticky="w", pady=(0, 6))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="w", pady=(12, 0))
        if event.link:
            ctk.CTkButton(actions, text=self.t("events.view_details") + " ↗", height=34,
                          corner_radius=8, font=self.font_small, fg_color=C["primary"],
                          hover_color=C["primary_hover"], text_color="#FFFFFF",
                          command=lambda u=event.link: webbrowser.open(u)).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(actions, text="📅 " + self.t("events.add_to_calendar"), height=34,
                      corner_radius=8, font=self.font_small, fg_color=C["surface_alt"],
                      hover_color=C["border"], text_color=C["text"],
                      command=lambda e=event: self._export_one(e)).grid(row=0, column=1)

    def _update_header_metrics(self, events: list) -> None:
        if not hasattr(self, "stat_total") or not self.stat_total.winfo_exists():
            return
        live = sum(1 for e in events if e.status() == "active")
        upcoming = sum(1 for e in events if e.status() == "upcoming")
        self.stat_live.configure(text="● " + self.t("events.stat_live", n=live))
        self.stat_upcoming.configure(text="● " + self.t("events.stat_upcoming", n=upcoming))
        self.stat_total.configure(text=self.t("events.stat_total", n=len(events)))
        self._refresh_updated_label()

    # ------------------------------------------------------------------ #
    # Settings view                                                      #
    # ------------------------------------------------------------------ #
    def _build_settings_view(self) -> None:
        scroll = ctk.CTkScrollableFrame(
            self.content, fg_color="transparent",
            scrollbar_button_color=C["surface_alt"], scrollbar_button_hover_color=C["border"],
        )
        scroll.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=24, pady=20)
        scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            scroll, text=self.t("settings.title"), font=self.font_title, text_color=C["text"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 16))

        # Language
        card = self._settings_card(scroll, 1, self.t("settings.language"))
        codes = self.service.translator.available_languages()
        names = [self.service.translator.language_name(c) for c in codes]
        self._lang_code_by_name = dict(zip(names, codes))
        current_name = self.service.translator.language_name(self.service.translator.language)
        menu = ctk.CTkOptionMenu(
            card, values=names, command=self._on_language_change, width=220, font=self.font_body,
            fg_color=C["surface_alt"], button_color=C["primary"], button_hover_color=C["primary_hover"],
            text_color=C["text"], dropdown_fg_color=C["surface_alt"], dropdown_hover_color=C["border"],
            dropdown_text_color=C["text"],
        )
        menu.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))
        menu.set(current_name)

        # Regions
        card = self._settings_card(scroll, 2, self.t("settings.regions"))
        selected = set(self.service.config.get("regions", ["Global"]))
        self._region_vars = {}
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        for i, region in enumerate(REGIONS):
            var = ctk.BooleanVar(value=region in selected)
            self._region_vars[region] = var
            ctk.CTkCheckBox(
                grid, text=self.t(f"regions.{region}"), variable=var, font=self.font_body,
                fg_color=C["primary"], hover_color=C["primary_hover"], text_color=C["text"],
                border_color=C["border"], checkmark_color="#FFFFFF",
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=4)

        # Notifications
        card = self._settings_card(scroll, 3, self.t("settings.notifications"))
        self._notif_var = ctk.BooleanVar(value=bool(self.service.config.get("notifications", True)))
        ctk.CTkCheckBox(
            card, text=self.t("settings.notifications_hint"), variable=self._notif_var,
            font=self.font_body, fg_color=C["primary"], hover_color=C["primary_hover"],
            text_color=C["text"], border_color=C["border"], checkmark_color="#FFFFFF",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 6))
        self._notif_fav_var = ctk.BooleanVar(value=bool(self.service.config.get("notify_favorites_only", False)))
        ctk.CTkCheckBox(
            card, text=self.t("settings.notify_favorites"), variable=self._notif_fav_var,
            font=self.font_body, fg_color=C["primary"], hover_color=C["primary_hover"],
            text_color=C["text"], border_color=C["border"], checkmark_color="#FFFFFF",
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 14))

        # Webhook (custom URL)
        card = self._settings_card(scroll, 4, self.t("settings.webhook"))
        ctk.CTkLabel(
            card, text=self.t("settings.webhook_hint"), font=self.font_small,
            text_color=C["text_muted"], wraplength=520, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 6))
        self.webhook_entry = ctk.CTkEntry(
            card, font=self.font_body, fg_color=C["surface_alt"], border_color=C["border"],
            text_color=C["text"], placeholder_text=self.t("settings.webhook_placeholder"),
        )
        self.webhook_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        existing_url = self.service.config.get("webhook_url", "")
        if existing_url:
            self.webhook_entry.insert(0, existing_url)
        wrow = ctk.CTkFrame(card, fg_color="transparent")
        wrow.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkButton(
            wrow, text=self.t("settings.webhook_test"), height=30, width=120, corner_radius=6,
            font=self.font_small, fg_color=C["surface_alt"], hover_color=C["border"],
            text_color=C["text"], command=self._on_test_webhook,
        ).grid(row=0, column=0)
        self.webhook_status = ctk.CTkLabel(wrow, text="", font=self.font_small, text_color=C["text_muted"])
        self.webhook_status.grid(row=0, column=1, padx=(10, 0))
        # Webhook secret (HMAC signing key) — masked entry.
        ctk.CTkLabel(
            card, text=self.t("settings.webhook_secret"), font=self.font_small,
            text_color=C["text_muted"],
        ).grid(row=4, column=0, sticky="w", padx=16, pady=(2, 0))
        self.webhook_secret_entry = ctk.CTkEntry(
            card, font=self.font_body, fg_color=C["surface_alt"], border_color=C["border"],
            text_color=C["text"], show="•",
        )
        self.webhook_secret_entry.grid(row=5, column=0, sticky="ew", padx=16, pady=(2, 4))
        secret = self.service.config.get("webhook_secret", "")
        if secret:
            self.webhook_secret_entry.insert(0, secret)
        ctk.CTkLabel(
            card, text=self.t("settings.webhook_secret_hint"), font=self.font_small,
            text_color=C["text_faint"], wraplength=520, justify="left",
        ).grid(row=6, column=0, sticky="w", padx=16, pady=(0, 12))

        # Refresh interval
        card = self._settings_card(scroll, 5, self.t("settings.refresh_interval"))
        self.interval_entry = ctk.CTkEntry(
            card, width=120, font=self.font_body, fg_color=C["surface_alt"],
            border_color=C["border"], text_color=C["text"],
        )
        self.interval_entry.insert(0, str(self.service.config.get("refresh_interval_minutes", 60)))
        self.interval_entry.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))

        # Configuration import / export
        card = self._settings_card(scroll, 6, self.t("settings.config"))
        crow = ctk.CTkFrame(card, fg_color="transparent")
        crow.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 6))
        ctk.CTkButton(
            crow, text=self.t("settings.export_config"), height=32, width=150, corner_radius=6,
            font=self.font_small, fg_color=C["surface_alt"], hover_color=C["border"],
            text_color=C["text"], command=self._on_export_config,
        ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(
            crow, text=self.t("settings.import_config"), height=32, width=150, corner_radius=6,
            font=self.font_small, fg_color=C["surface_alt"], hover_color=C["border"],
            text_color=C["text"], command=self._on_import_config,
        ).grid(row=0, column=1)
        self.config_status = ctk.CTkLabel(card, text="", font=self.font_small, text_color=C["text_muted"])
        self.config_status.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 12))

        # Telegram alerts
        card = self._settings_card(scroll, 7, self.t("settings.telegram"))
        self.tg_token_entry = ctk.CTkEntry(
            card, font=self.font_body, fg_color=C["surface_alt"], border_color=C["border"],
            text_color=C["text"], show="•", placeholder_text=self.t("settings.telegram_token"),
        )
        self.tg_token_entry.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        tok = self.service.config.get("telegram_bot_token", "")
        if tok:
            self.tg_token_entry.insert(0, tok)
        self.tg_chat_entry = ctk.CTkEntry(
            card, font=self.font_body, fg_color=C["surface_alt"], border_color=C["border"],
            text_color=C["text"], placeholder_text=self.t("settings.telegram_chat"),
        )
        self.tg_chat_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        chat = self.service.config.get("telegram_chat_id", "")
        if chat:
            self.tg_chat_entry.insert(0, chat)

        # Time format + display timezone
        card = self._settings_card(scroll, 8, self.t("settings.time_format"))
        trow = ctk.CTkFrame(card, fg_color="transparent")
        trow.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))
        self.time_fmt_menu = ctk.CTkOptionMenu(
            trow, values=[self.t("settings.time_24h"), self.t("settings.time_12h")], width=130,
            font=self.font_body, fg_color=C["surface_alt"], button_color=C["primary"],
            button_hover_color=C["primary_hover"], text_color=C["text"],
            dropdown_fg_color=C["surface_alt"], dropdown_hover_color=C["border"], dropdown_text_color=C["text"],
        )
        self.time_fmt_menu.grid(row=0, column=0, padx=(0, 10))
        self.time_fmt_menu.set(
            self.t("settings.time_12h") if self.service.config.get("time_format") == "12h"
            else self.t("settings.time_24h")
        )
        self.tz_entry = ctk.CTkEntry(
            trow, width=200, font=self.font_body, fg_color=C["surface_alt"], border_color=C["border"],
            text_color=C["text"], placeholder_text=self.t("settings.timezone"),
        )
        self.tz_entry.grid(row=0, column=1)
        tz = self.service.config.get("display_timezone", "")
        if tz:
            self.tz_entry.insert(0, tz)

        # Minimize to tray
        card = self._settings_card(scroll, 9, self.t("settings.tray"))
        self._tray_var = ctk.BooleanVar(value=bool(self.service.config.get("close_to_tray", False)))
        ctk.CTkCheckBox(
            card, text=self.t("settings.tray"), variable=self._tray_var, font=self.font_body,
            fg_color=C["primary"], hover_color=C["primary_hover"], text_color=C["text"],
            border_color=C["border"], checkmark_color="#FFFFFF",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))

        ctk.CTkButton(
            scroll, text=self.t("settings.save"), height=40, width=160, corner_radius=8,
            font=self.font_body, fg_color=C["primary"], hover_color=C["primary_hover"],
            text_color="#FFFFFF", command=self._on_save_settings,
        ).grid(row=10, column=0, sticky="w", pady=(6, 4))
        self.saved_label = ctk.CTkLabel(scroll, text="", font=self.font_small, text_color=C["success"])
        self.saved_label.grid(row=11, column=0, sticky="w", pady=(0, 8))

    def _settings_card(self, parent, row: int, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.grid(row=row, column=0, sticky="ew", pady=8)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=self.font_section, text_color=C["text"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 6)
        )
        return card

    # ------------------------------------------------------------------ #
    # Filter helpers                                                     #
    # ------------------------------------------------------------------ #
    def _type_display(self, raw: str | None) -> str:
        if not raw:
            return self.t("events.all_types")
        return raw.replace("-", " ").title()

    def _on_search_key(self, _event=None) -> None:
        # Debounce: re-render 300 ms after the last keystroke.
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:  # noqa: BLE001
                pass
        self._search_job = self.after(300, self._apply_search)

    def _apply_search(self) -> None:
        self._search_job = None
        if hasattr(self, "search_entry") and self.search_entry.winfo_exists():
            self._search_text = self.search_entry.get().strip()
            self._render_events()

    def _on_type_change(self, display: str) -> None:
        if display == self.t("events.all_types"):
            self._type_filter = None
        else:
            for raw in self.service.available_types():
                if self._type_display(raw) == display:
                    self._type_filter = raw
                    break
        self._render_events()

    def _on_toggle_favorites(self) -> None:
        self._favorites_only = not self._favorites_only
        if hasattr(self, "fav_btn") and self.fav_btn.winfo_exists():
            self.fav_btn.configure(
                fg_color=C["primary"] if self._favorites_only else C["surface_alt"],
                text_color="#FFFFFF" if self._favorites_only else C["text"],
            )
        self._render_events()

    def _current_filtered_events(self) -> list:
        return self.service.get_events(
            search=self._search_text or None,
            event_types=[self._type_filter] if self._type_filter else None,
            favorites_only=self._favorites_only,
        )

    def _on_export_calendar(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".ics", initialfile="poketrack.ics",
            filetypes=[("iCalendar", "*.ics"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.service.export_calendar(path, self._current_filtered_events())
            self._set_status(self.t("events.export_calendar") + " ✓", C["success"])
        except OSError as exc:  # noqa: BLE001
            logger.error("Calendar export failed: %s", exc)

    def _export_one(self, event) -> None:
        safe = "".join(c if c.isalnum() else "_" for c in event.event_id)[:50] or "event"
        path = filedialog.asksaveasfilename(
            defaultextension=".ics", initialfile=f"{safe}.ics",
            filetypes=[("iCalendar", "*.ics")],
        )
        if not path:
            return
        try:
            self.service.export_calendar(path, [event])
        except OSError as exc:  # noqa: BLE001
            logger.error("ICS export failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Event handlers                                                     #
    # ------------------------------------------------------------------ #
    def _on_language_change(self, name: str) -> None:
        code = self._lang_code_by_name.get(name)
        if code:
            self.service.set_language(code)
            self.title(self.t("app.title"))
            self._build_ui()

    def _on_save_settings(self) -> None:
        regions = [r for r, var in self._region_vars.items() if var.get()]
        self.service.set_regions(regions)
        self.service.set_notifications(self._notif_var.get())
        self.service.set_notify_favorites_only(self._notif_fav_var.get())
        self.service.set_webhook(self.webhook_entry.get())
        self.service.set_webhook_secret(self.webhook_secret_entry.get())
        self.service.set_telegram(self.tg_token_entry.get(), self.tg_chat_entry.get())
        self.service.set_time_format(
            "12h" if self.time_fmt_menu.get() == self.t("settings.time_12h") else "24h"
        )
        self.service.set_display_timezone(self.tz_entry.get())
        self.service.set_close_to_tray(self._tray_var.get())
        try:
            minutes = int(self.interval_entry.get())
        except (ValueError, TypeError):
            minutes = self.service.config.get("refresh_interval_minutes", 60)
        self.service.set_interval(minutes)
        self.saved_label.configure(text=self.t("settings.saved"))

    def _on_test_webhook(self) -> None:
        url = self.webhook_entry.get().strip()
        if not url:
            return
        self.service.set_webhook(url)  # persist what was typed before testing
        if hasattr(self, "webhook_status") and self.webhook_status.winfo_exists():
            self.webhook_status.configure(text="…", text_color=C["text_muted"])
        threading.Thread(target=self._test_webhook_worker, args=(url,), daemon=True).start()

    def _test_webhook_worker(self, url: str) -> None:
        ok, info = self.service.send_test_webhook(url)
        self._ui_queue.put(("webhook_test", (ok, info)))

    def _on_refresh(self) -> None:
        self.refresh_btn.configure(state="disabled")
        self._set_status(self.t("status.fetching"), C["accent"])
        # Run the async refresh on the shared event loop — never blocks Tk.
        future = RUNNER.submit(self.service.refresh_now_async(trigger_side_effects=True))
        future.add_done_callback(self._on_async_refresh_done)

    def _on_async_refresh_done(self, future) -> None:
        # Runs on the async loop thread — only enqueue; the Tk poll loop renders.
        try:
            result = future.result()
        except Exception:  # noqa: BLE001
            logger.exception("Async refresh failed")
            result = RefreshResult(False, error_key="errors.generic")
        self._ui_queue.put(("manual", result))

    # --- config import/export -------------------------------------------- #
    def _on_export_config(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile="poketrack-config.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.service.export_config(path)
            self._set_config_status(self.t("settings.config_exported"), C["success"])
        except OSError as exc:
            logger.error("Config export failed: %s", exc)
            self._set_config_status(self.t("settings.config_import_failed"), C["danger"])

    def _on_import_config(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        ok, info = self.service.import_config(path)
        if ok:
            # Rebuild so language/regions/etc. from the imported file take effect,
            # then report success on the freshly-built settings view.
            self.title(self.t("app.title"))
            self._build_ui()
            self._set_config_status(self.t("settings.config_imported"), C["success"])
        else:
            logger.warning("Config import failed: %s", info)
            self._set_config_status(self.t("settings.config_import_failed"), C["danger"])

    def _set_config_status(self, text: str, color: str) -> None:
        if hasattr(self, "config_status") and self.config_status.winfo_exists():
            self.config_status.configure(text=text, text_color=color)

    def _open_web(self) -> None:
        host = self.service.config.get("web.host", "127.0.0.1")
        port = self.service.config.get("web.port", 5000)
        url = f"http://{host}:{port}/"
        # In a frozen build there's no run_web.py beside the exe to launch.
        if not getattr(sys, "frozen", False):
            if self._web_proc is None or self._web_proc.poll() is not None:
                try:
                    self._web_proc = subprocess.Popen(
                        [sys.executable, str(ROOT / "run_web.py")], cwd=str(ROOT)
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("Could not start web server: %s", exc)
        self.after(1500, lambda: webbrowser.open(url))

    # ------------------------------------------------------------------ #
    # Cross-thread queue + periodic tick                                 #
    # ------------------------------------------------------------------ #
    def _on_image_ready(self, url: str, pil_image) -> None:
        # Called on a worker thread — only enqueue; never touch Tk here.
        self._ui_queue.put(("image", (url, pil_image)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "image":
                    self._apply_image(*payload)
                elif kind == "webhook_test":
                    self._apply_webhook_test(*payload)
                elif kind == "tray":
                    self._handle_tray(payload)
                else:
                    self._handle_refresh_result(kind, payload)
        except queue.Empty:
            pass
        finally:
            self.after(200, self._poll_queue)

    def _handle_tray(self, action: str) -> None:
        if action == "show":
            try:
                self.deiconify()
                self.lift()
            except Exception:  # noqa: BLE001
                pass
        elif action == "refresh":
            self._on_refresh()
        elif action == "quit":
            self._shutdown()

    def _apply_webhook_test(self, ok: bool, info: str) -> None:
        if hasattr(self, "webhook_status") and self.webhook_status.winfo_exists():
            key = "settings.webhook_ok" if ok else "settings.webhook_fail"
            self.webhook_status.configure(
                text=self.t(key), text_color=C["success"] if ok else C["danger"]
            )
        logger.info("Webhook test result: ok=%s (%s)", ok, info)

    def _apply_image(self, url: str, pil_image) -> None:
        if url not in self._img_cache:
            try:
                self._img_cache[url] = ctk.CTkImage(
                    light_image=pil_image, dark_image=pil_image, size=pil_image.size
                )
            except Exception:  # noqa: BLE001
                return
        image = self._img_cache[url]
        for label in self._img_pending.pop(url, []):
            try:
                if label.winfo_exists():
                    label.configure(image=image)
            except Exception:  # noqa: BLE001
                pass

    def _handle_refresh_result(self, source: str, result: RefreshResult) -> None:
        self._loading = False  # first result in — stop showing the skeleton
        if hasattr(self, "refresh_btn") and self.refresh_btn.winfo_exists():
            self.refresh_btn.configure(state="normal")
        if not result.ok:
            self._set_status(self.t(result.error_key or "errors.generic"), C["danger"])
        elif result.new_count and not result.first_load:
            self._set_status(self.t("events.new_found", n=result.new_count), C["accent"])
        else:
            self._set_status(self.t("status.updated"), C["success"])
        if self._current_view == "events":
            self._render_events()

    def _tick(self) -> None:
        """Re-render periodically so LIVE/SOON badges + countdowns stay accurate."""
        if self._current_view == "events":
            self._render_events()
        self.after(60_000, self._tick)

    # ------------------------------------------------------------------ #
    # Status helpers + teardown                                          #
    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, color: str) -> None:
        if hasattr(self, "status_label") and self.status_label.winfo_exists():
            self.status_label.configure(text=text, text_color=color)

    def _refresh_updated_label(self) -> None:
        if hasattr(self, "updated_label") and self.updated_label.winfo_exists():
            last = self.service.last_updated()
            last_text = last.strftime("%b %d, %Y · %H:%M") if last else "—"
            self.updated_label.configure(text=self.t("events.last_updated", time=last_text))

    def _on_close(self) -> None:
        # Optionally minimize to the system tray instead of quitting.
        if self.service.config.get("close_to_tray", False) and tray_mod.available():
            self._hide_to_tray()
            return
        self._shutdown()

    def _hide_to_tray(self) -> None:
        self.withdraw()
        if self._tray is None:
            self._tray = tray_mod.TrayIcon(
                on_show=lambda: self._ui_queue.put(("tray", "show")),
                on_refresh=lambda: self._ui_queue.put(("tray", "refresh")),
                on_quit=lambda: self._ui_queue.put(("tray", "quit")),
                title=self.t("app.title"),
                labels=(self.t("nav.events"), self.t("nav.refresh"), "Quit"),
            )
            if not self._tray.start():
                self._tray = None
                self._shutdown()

    def _shutdown(self) -> None:
        for shutdown in (self._image_loader.shutdown, RUNNER.shutdown):
            try:
                shutdown()
            except Exception:  # noqa: BLE001
                pass
        if self._tray is not None:
            self._tray.stop()
        self.destroy()
