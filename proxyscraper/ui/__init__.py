"""Terminal-Oberfläche: Bausteine (widgets), Live-Ansichten (dashboard) und Abschlussbericht (report).

Die Konsole wird bewusst nicht re-exportiert: Wer ausgibt, nutzt `widgets.console` zur Laufzeit,
damit sie sich austauschen lässt (z. B. zum Aufzeichnen von Screenshots oder in Tests).
"""

from . import widgets
from .dashboard import CheckDashboard, CollectView, LiveStats
from .report import render_source_ranking, render_summary
from .widgets import (
    ACCENT,
    BAD,
    BLOCKED_HIT_RATE,
    BORDER,
    GOOD,
    MUTED,
    WARN,
    banner,
    bar,
    fmt,
    fmt_duration,
    info,
    note,
    pct,
    section,
    section_end,
    short_url,
)

__all__ = [
    "ACCENT", "BAD", "BORDER", "BLOCKED_HIT_RATE", "GOOD", "MUTED", "WARN",
    "CheckDashboard", "CollectView", "LiveStats",
    "banner", "bar", "fmt", "fmt_duration", "info", "note", "pct", "section", "section_end", "short_url",
    "render_source_ranking", "render_summary", "widgets",
]
