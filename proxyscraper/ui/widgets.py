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

from .. import __version__
from ..geo import flag

console = Console(highlight=False)

# Eine Palette für alles (auch im Profil/README verwendet). rich rechnet sie auf Terminals mit
# weniger Farben automatisch herunter.
ACCENT = "#38BDF8"
GOOD = "#34D399"
WARN = "#FBBF24"
BAD = "#F87171"
MUTED = "#8B949E"
BORDER = "#30363D"
TYPE_STYLE = {"http": "#60A5FA", "socks4": "#C084FC", "socks5": "#34D399"}
ANON_STYLE = {"elite": ("E", GOOD), "anonymous": ("A", WARN), "transparent": ("T", BAD)}
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
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(
        Text.assemble(("⚡ proxy-scraper", f"bold {ACCENT}"), (f"  v{__version__}", MUTED)),
        Text(datetime.now().strftime("%d.%m.%Y  %H:%M"), style=MUTED),
    )
    grid.add_row(Text("Freie Proxys, die wirklich funktionieren – gesammelt, geprüft, gelernt.", style=MUTED), "")
    return Panel(grid, box=box.ROUNDED, border_style=ACCENT, padding=(0, 2))


def phase_bar(current: int) -> Text:
    text = Text()
    for i, name in enumerate(PHASES):
        if i:
            text.append("  ─  ", style=GOOD if i <= current else BORDER)
        if i < current:
            text.append(f"✔ {name}", style=GOOD)
        elif i == current:
            text.append(f"● {i + 1} {name}", style=f"bold {ACCENT}")
        else:
            text.append(f"○ {i + 1} {name}", style=MUTED)
    return text


def header(current: int, started: float) -> Table:
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(phase_bar(current), Text(f"⏱ {fmt_duration(time.perf_counter() - started)}", style=MUTED))
    return grid


_section_open = False


def section(title: str) -> None:
    """Beginnt einen Abschnitt; folgende info()/note()-Zeilen hängen an seiner linken Rahmenlinie."""
    global _section_open
    if _section_open:
        section_end()
    line = Text()
    line.append("  ╭─ ", style=BORDER)
    line.append(title, style=f"bold {ACCENT}")
    line.append(" ", style=BORDER)
    line.append("─" * max(console.size.width - line.cell_len - 2, 4), style=BORDER)
    console.print(line)
    _section_open = True


def section_end() -> None:
    global _section_open
    if _section_open:
        console.print(Text("  ╰─", style=BORDER))
        _section_open = False


def _gutter() -> Text:
    # Farbe nur für das Rahmenzeichen – nicht als Grundstil, der sonst auf die ganze Zeile abfärbt
    gutter = Text()
    gutter.append("  │  " if _section_open else "  ", style=BORDER)
    return gutter


def info(label: str, value, style: str = "") -> None:
    """Einheitliche Info-Zeile – im Abschnitt mit Rahmenlinie, sonst eingerückt."""
    line = _gutter()
    line.append(f"{label:<14}", style=MUTED)
    line.append_text(value if isinstance(value, Text) else Text(str(value), style=style or "bold"))
    console.print(line)


def note(message: str, style: str = WARN, icon: str = "⚠") -> None:
    console.print(_gutter() + Text(f"{icon} ", style=style) + Text.from_markup(message))


def card(label: str, value: str, sub, style: str = "bold") -> Panel:
    # Alle Karten einer Reihe sollen gleich hoch bleiben – lange Untertitel werden gekürzt statt umbrochen
    sub = sub if isinstance(sub, Text) else Text(sub, style=MUTED)
    sub.no_wrap, sub.overflow = True, "ellipsis"
    body = Group(Text(label.upper(), style=f"bold {MUTED}"), Text(value, style=style), sub)
    return Panel(body, box=box.ROUNDED, border_style=BORDER, padding=(0, 1))


def table(**kwargs) -> Table:
    """Einheitliche, luftige Tabelle ohne Rahmenlinien (der Rahmen kommt vom Panel)."""
    kwargs.setdefault("expand", True)
    return Table(box=None, header_style=f"bold {MUTED}", pad_edge=False, **kwargs)


def panel_title(title: str, style: str = BORDER) -> Text:
    """Titel lesbar halten: bei dezentem Rahmen gedämpft-hell statt in der dunklen Rahmenfarbe."""
    return Text(f" {title} ", style=f"bold {MUTED if style == BORDER else style}")


def panel(renderable, title: str, style: str = BORDER, **kwargs) -> Panel:
    return Panel(renderable, title=panel_title(title, style), title_align="left", box=box.ROUNDED,
                 border_style=style, **kwargs)


def row(*renderables, ratios: Optional[Sequence[int]] = None) -> Table:
    grid = Table.grid(expand=True)
    for i, _ in enumerate(renderables):
        grid.add_column(ratio=(ratios[i] if ratios else 1))
    grid.add_row(*renderables)
    return grid


def centered(text: str, style: str = MUTED) -> Align:
    return Align.center(Text(text, style=style))
