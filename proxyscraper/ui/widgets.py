"""Farben, Formatierung und wiederverwendbare Bausteine für die Terminal-Oberfläche."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional, Sequence

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import ProgressColumn
from rich.table import Table
from rich.text import Text

from ..geo import flag

console = Console(highlight=False)

ACCENT = "bright_cyan"
GOOD = "green"
WARN = "yellow"
BAD = "red"
MUTED = "grey50"
TYPE_STYLE = {"http": "cyan", "socks4": "magenta", "socks5": "bright_green"}
ANON_STYLE = {"elite": ("E", "green"), "anonymous": ("A", "yellow"), "transparent": ("T", "red")}
ANON_LABEL = {"elite": "Elite", "anonymous": "Anonym", "transparent": "Transp."}
PHASES = ("Quellen", "Sammeln", "Prüfen", "Fertig")
SPARK = "▁▂▃▄▅▆▇█"
LATENCY_EDGES = (300, 700, 1500, 3000, 6000)
LATENCY_LABELS = ("< 0,3 s", "< 0,7 s", "< 1,5 s", "< 3 s", "< 6 s", "≥ 6 s")
# Unter 0,2 % Treffern blockiert das Netz vermutlich Proxy-Verbindungen (Firewall)
BLOCKED_HIT_RATE = 0.002


# --------------------------------------------------------------------------- #
# Formatierung
# --------------------------------------------------------------------------- #

def fmt(n: float) -> str:
    """Tausenderpunkte wie im Deutschen: 12345 -> 12.345"""
    return f"{n:,.0f}".replace(",", ".")


def pct(part: float, whole: float) -> str:
    return f"{part / whole * 100:.1f} %".replace(".", ",") if whole else "–"


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m} min {s:02d} s"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min"


def latency_style(ms: int) -> str:
    return GOOD if ms < 1000 else WARN if ms < 3000 else BAD


def bar(value: float, maximum: float, width: int, style: str) -> Text:
    """Balken mit Achtelschritten für feine Auflösung auf wenig Platz."""
    width = max(width, 1)
    filled = 0 if maximum <= 0 else min(value / maximum, 1.0) * width
    full = int(filled)
    rest = int((filled - full) * 8)
    text = Text("█" * full, style=style)
    if rest and full < width:
        text.append(" ▏▎▍▌▋▊▉"[rest], style=style)
        full += 1
    text.append("·" * (width - full), style=MUTED)
    return text


def sparkline(values: Sequence[float], width: int) -> Text:
    values = list(values)[-width:]
    if not values:
        return Text("")
    hi = max(values) or 1
    return Text("".join(SPARK[min(int(v / hi * (len(SPARK) - 1) + 0.5), len(SPARK) - 1)] for v in values), style=ACCENT)


def type_badge(ptype: str) -> Text:
    return Text(ptype, style=f"bold {TYPE_STYLE.get(ptype, 'white')}")


def country_cell(cc: str) -> Text:
    return Text(f"{flag(cc)} {cc}" if cc else "  ··", style="" if cc else MUTED)


def https_cell(value: Optional[bool]) -> Text:
    if value is None:
        return Text("·", style=MUTED)
    return Text("✔", style=GOOD) if value else Text("✘", style=BAD)


def anon_cell(level: str) -> Text:
    letter, style = ANON_STYLE.get(level, ("·", MUTED))
    return Text(letter, style=f"bold {style}" if level else style)


def short_url(url: str) -> str:
    gh = "https://raw.githubusercontent.com/"
    if url.startswith(gh):
        return "gh:" + url[len(gh):]
    return url.split("://", 1)[-1]


class CountColumn(ProgressColumn):
    """12.345 / 1.000.000 statt 12345/1000000."""

    def render(self, task) -> Text:
        return Text.assemble((fmt(task.completed), "bold"), (f" / {fmt(task.total or 0)}", MUTED))


# --------------------------------------------------------------------------- #
# Bausteine
# --------------------------------------------------------------------------- #

def banner() -> Panel:
    title = Text.assemble(("⚡ PROXY SCRAPER", f"bold {ACCENT}"), ("  ·  sammeln · prüfen · lernen", MUTED))
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(title, Text(datetime.now().strftime("%d.%m.%Y  %H:%M"), style=MUTED))
    return Panel(grid, box=box.HEAVY, border_style=ACCENT, padding=(0, 1))


def phase_bar(current: int) -> Text:
    text = Text()
    for i, name in enumerate(PHASES):
        if i:
            text.append(" ── ", style=GOOD if i <= current else MUTED)
        if i < current:
            text.append(f"✔ {name}", style=GOOD)
        elif i == current:
            text.append(f"◉ {name}", style=f"bold {ACCENT}")
        else:
            text.append(f"○ {name}", style=MUTED)
    return text


def header(current: int, started: float) -> Table:
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(phase_bar(current), Text(f"⏱ {fmt_duration(time.perf_counter() - started)}", style=MUTED))
    return grid


def info(label: str, value, style: str = "") -> None:
    """Einheitliche Info-Zeile vor/zwischen den Phasen."""
    line = Text("  ▸ ", style=ACCENT)
    line.append(f"{label:<14}", style="bold")
    line.append_text(value if isinstance(value, Text) else Text(str(value), style=style))
    console.print(line)


def note(message: str, style: str = WARN, icon: str = "⚠") -> None:
    console.print(Text(f"  {icon} ", style=style) + Text.from_markup(message))


def card(label: str, value: str, sub, style: str = "bold") -> Panel:
    body = Group(
        Text(label, style=MUTED),
        Text(value, style=style),
        sub if isinstance(sub, Text) else Text(sub, style=MUTED),
    )
    return Panel(body, box=box.ROUNDED, border_style=MUTED, padding=(0, 1))


def table(**kwargs) -> Table:
    """Einheitliche, luftige Tabelle ohne Rahmenlinien (der Rahmen kommt vom Panel)."""
    kwargs.setdefault("expand", True)
    return Table(box=None, header_style=f"bold {MUTED}", pad_edge=False, **kwargs)


def panel(renderable, title: str, style: str = MUTED, **kwargs) -> Panel:
    return Panel(renderable, title=title, title_align="left", box=box.ROUNDED, border_style=style, **kwargs)


def row(*renderables, ratios: Optional[Sequence[int]] = None) -> Table:
    grid = Table.grid(expand=True)
    for i, _ in enumerate(renderables):
        grid.add_column(ratio=(ratios[i] if ratios else 1))
    grid.add_row(*renderables)
    return grid


def centered(text: str, style: str = MUTED) -> Align:
    return Align.center(Text(text, style=style))
