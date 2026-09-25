"""Terminal UI: building blocks (widgets), live views (dashboard) and the final report (report).

The console is deliberately not re-exported: whatever prints uses `widgets.console` at runtime,
so it can be swapped (e.g. for recording screenshots or in tests).
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
    "ACCENT",
    "BAD",
    "BLOCKED_HIT_RATE",
    "BORDER",
    "GOOD",
    "MUTED",
    "WARN",
    "CheckDashboard",
    "CollectView",
    "LiveStats",
    "banner",
    "bar",
    "fmt",
    "fmt_duration",
    "info",
    "note",
    "pct",
    "render_source_ranking",
    "render_summary",
    "section",
    "section_end",
    "short_url",
    "widgets",
]
