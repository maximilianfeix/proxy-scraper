"""Colors, formatting and reusable building blocks for the terminal UI."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional, Sequence
from urllib.parse import unquote

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

# One palette for everything (the lime is the brand color of the logo and the website). rich
# downsamples it automatically on terminals with fewer colors.
ACCENT = "#D4F77A"
GOOD = "#34D399"
WARN = "#FBBF24"
BAD = "#F87171"
MUTED = "#8B949E"
BORDER = "#30363D"
TYPE_STYLE = {"http": "#60A5FA", "socks4": "#C084FC", "socks5": "#34D399"}
ANON_STYLE = {"elite": ("E", GOOD), "anonymous": ("A", WARN), "transparent": ("T", BAD)}
ANON_LABEL = {"elite": "Elite", "anonymous": "Anonymous", "transparent": "Transp."}
PHASES = ("Sources", "Collect", "Check", "Done")
SPARK = "▁▂▃▄▅▆▇█"
LATENCY_EDGES = (300, 700, 1500, 3000, 6000)
LATENCY_LABELS = ("< 0.3 s", "< 0.7 s", "< 1.5 s", "< 3 s", "< 6 s", "≥ 6 s")
# below a 0.2 % hit rate the network is probably blocking proxy connections (firewall)
BLOCKED_HIT_RATE = 0.002


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #

def fmt(n: float) -> str:
    """Thousands separators: 12345 -> 12,345"""
    return f"{n:,.0f}"


def pct(part: float, whole: float) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "–"


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
    """Bar with eighth steps for fine resolution in little space."""
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
    """12,345 / 1,000,000 instead of 12345/1000000."""

    def render(self, task) -> Text:
        return Text.assemble((fmt(task.completed), "bold"), (f" / {fmt(task.total or 0)}", MUTED))


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #

def banner() -> Panel:
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(
        Text.assemble(("◆ proxy-scraper", f"bold {ACCENT}"), (f"  v{__version__}", MUTED)),
        Text(datetime.now().strftime("%Y-%m-%d  %H:%M"), style=MUTED),
    )
    grid.add_row(Text("Free proxies that actually work – collected, checked, learned.", style=MUTED), "")
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
    """Starts a section; the following info()/note() lines hang off its left border line."""
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
    # color only for the border character – not as the base style, which would bleed into the whole line
    gutter = Text()
    gutter.append("  │  " if _section_open else "  ", style=BORDER)
    return gutter


def info(label: str, value, style: str = "") -> None:
    """Uniform info line – with a border line inside a section, indented otherwise."""
    line = _gutter()
    line.append(f"{label:<14}", style=MUTED)
    line.append_text(value if isinstance(value, Text) else Text(str(value), style=style or "bold"))
    console.print(line)


def note(message: str, style: str = WARN, icon: str = "⚠") -> None:
    console.print(_gutter() + Text(f"{icon} ", style=style) + Text.from_markup(message))


def card(label: str, value: str, sub, style: str = "bold") -> Panel:
    # all cards in a row should stay the same height – long subtitles are shortened instead of wrapped
    sub = sub if isinstance(sub, Text) else Text(sub, style=MUTED)
    sub.no_wrap, sub.overflow = True, "ellipsis"
    body = Group(Text(label.upper(), style=f"bold {MUTED}"), Text(value, style=style), sub)
    return Panel(body, box=box.ROUNDED, border_style=BORDER, padding=(0, 1))


def table(**kwargs) -> Table:
    """Uniform, airy table without border lines (the frame comes from the panel)."""
    kwargs.setdefault("expand", True)
    return Table(box=None, header_style=f"bold {MUTED}", pad_edge=False, **kwargs)


def panel_title(title: str, style: str = BORDER) -> Text:
    """Keep titles readable: with a subtle frame, muted-light instead of the dark frame color."""
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


def shown_proxy(proxy: str) -> str:
    """Proxy for the terminal: passwords are masked ('alice:•••@1.2.3.4:1080'), the files keep them."""
    auth, sep, address = proxy.rpartition("@")
    if not sep:
        return proxy
    user = unquote(auth.partition(":")[0])
    # user names come from third-party lists – never let control characters (newline, ESC) into the terminal
    user = "".join(c if c.isprintable() else "?" for c in user)
    return f"{user}:•••@{address}"
