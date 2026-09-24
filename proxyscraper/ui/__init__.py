"""Terminal-Oberfläche: Bausteine (widgets), Live-Ansichten (dashboard) und Abschlussbericht (report)."""

from . import widgets
from .dashboard import CheckDashboard, CollectView, LiveStats
from .report import render_source_ranking, render_summary
from .widgets import (
    ACCENT,
    BAD,
    BLOCKED_HIT_RATE,
    GOOD,
    MUTED,
    WARN,
    banner,
    bar,
    console,
    fmt,
    fmt_duration,
    info,
    note,
    pct,
    short_url,
)

__all__ = [
    "ACCENT", "BAD", "BLOCKED_HIT_RATE", "GOOD", "MUTED", "WARN",
    "CheckDashboard", "CollectView", "LiveStats",
    "banner", "bar", "console", "fmt", "fmt_duration", "info", "note", "pct", "short_url",
    "render_source_ranking", "render_summary", "widgets",
]
