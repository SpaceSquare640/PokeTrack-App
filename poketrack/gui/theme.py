"""The "Midnight Blue" design system — the single source of truth for colours.

Both front-ends pull from :data:`MIDNIGHT_BLUE`:

* the CustomTkinter desktop UI reads the hex values directly;
* the Flask layer injects these *same* values into its Tailwind config and CSS
  variables (see ``web/templates/base.html``).

This module imports nothing UI-specific (no Tk, no Flask) so it can be shared
freely by either side without pulling in heavy dependencies.
"""
from __future__ import annotations

# Deep blues, charcoal grays, and slate accents.
MIDNIGHT_BLUE: dict[str, str] = {
    "bg":            "#0B1120",  # app background — deepest midnight
    "bg_alt":        "#0F172A",  # secondary background / sidebar
    "surface":       "#111827",  # cards / panels — charcoal
    "surface_alt":   "#1E293B",  # elevated surfaces — slate
    "border":        "#334155",  # slate accent border
    "primary":       "#3B82F6",  # primary action — blue
    "primary_hover": "#2563EB",  # primary hover
    "accent":        "#38BDF8",  # sky accent
    "text":          "#E2E8F0",  # primary text — slate-200
    "text_muted":    "#94A3B8",  # secondary text — slate-400
    "text_faint":    "#8091A8",  # tertiary text — lightened to clear WCAG AA (4.5:1+) on dark surfaces
    "success":       "#34D399",  # active / live
    "warning":       "#FBBF24",  # upcoming / soon
    "danger":        "#F87171",  # error / ended
    "on_primary":    "#FFFFFF",  # text/icon color on top of primary/brand-colored controls
}

# Light-theme counterpart ("Paper") — warm paper editorial tones. Same keys as
# MIDNIGHT_BLUE so either dict can drive the shared CSS-variable layer; the web
# UI ships both and toggles at runtime. All text colors clear WCAG AA on their
# respective surfaces.
PAPER_LIGHT: dict[str, str] = {
    "bg":            "#F7F6F2",  # warm paper background
    "bg_alt":        "#EFEEE8",  # secondary background / sidebar
    "surface":       "#FFFFFF",  # cards / panels
    "surface_alt":   "#F2F1EB",  # elevated surfaces
    "border":        "#E2E0D7",  # hairline borders
    "primary":       "#2563EB",  # primary action — blue
    "primary_hover": "#1D4ED8",  # primary hover
    "accent":        "#0369A1",  # deep sky accent (AA on paper)
    "text":          "#1C2430",  # primary text — near-ink
    "text_muted":    "#5B6878",  # secondary text
    "text_faint":    "#68758a",  # tertiary text (AA 4.5:1+ on bg/surface)
    "success":       "#0E9F6E",  # active / live
    "warning":       "#B45309",  # upcoming / soon
    "danger":        "#DC2626",  # error / ended
    "on_primary":    "#FFFFFF",
}

# Event status -> accent colour. Shared by both UIs so a "LIVE" badge is the
# same green everywhere.
STATUS_COLORS: dict[str, str] = {
    "active":   MIDNIGHT_BLUE["success"],
    "upcoming": MIDNIGHT_BLUE["warning"],
    "ended":    MIDNIGHT_BLUE["text_faint"],
    "unknown":  MIDNIGHT_BLUE["text_muted"],
}

# Clean default on Windows; tkinter/Tailwind fall back gracefully elsewhere.
FONT_FAMILY = "Segoe UI"


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, MIDNIGHT_BLUE["text_muted"])
