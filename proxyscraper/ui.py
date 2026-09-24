"""Terminal-Oberfläche mit rich: Banner, Phasenanzeige, Live-Dashboards und Abschlussbericht."""

from __future__ import annotations

import time
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    ProgressColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from .checker import CheckResult
from .geo import flag
from .parsing import PROXY_TYPES

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


# --------------------------------------------------------------------------- #
# Phase 2: Sammeln
# --------------------------------------------------------------------------- #

class CollectView:
    def __init__(self, total_sources: int, started: float):
        self.started = started
        self.ok = 0
        self.failed = 0
        self.bytes = 0
        self.unique = 0
        self.progress = Progress(
            SpinnerColumn(style=ACCENT),
            TextColumn("[bold]Lade & parse Quellen"),
            BarColumn(bar_width=None, complete_style=ACCENT, finished_style=GOOD),
            CountColumn(),
            TimeElapsedColumn(),
            expand=True,
        )
        self.task = self.progress.add_task("", total=total_sources)

    def advance(self) -> None:
        self.progress.advance(self.task)

    def __rich__(self):
        elapsed = max(time.perf_counter() - self.started, 1e-6)
        stats = row(
            card("Quellen OK", fmt(self.ok), f"{fmt(self.failed)} fehlgeschlagen", f"bold {GOOD}"),
            card("Geladen", f"{self.bytes / 2**20:,.0f} MB".replace(",", "."), f"{self.bytes / 2**20 / elapsed:.1f} MB/s"),
            card("Proxys", fmt(self.unique), "einzigartig", f"bold {ACCENT}"),
        )
        return Group(
            header(1, self.started),
            Panel(Group(self.progress, stats), box=box.ROUNDED, border_style=ACCENT, title="Sammeln", title_align="left"),
        )


# --------------------------------------------------------------------------- #
# Phase 3: Prüfen
# --------------------------------------------------------------------------- #

class LiveStats:
    def __init__(self, jobs_by_type: Dict[str, int]):
        self.total = sum(jobs_by_type.values())
        self.total_by_type = dict(jobs_by_type)
        self.checked = 0
        self.checked_by_type: Counter = Counter()
        self.working_by_type: Counter = Counter()
        self.latency_hist = [0] * len(LATENCY_LABELS)
        self.latency_sum = 0
        self.fastest: Optional[int] = None
        self.countries: Counter = Counter()
        self.https_ok = 0
        self.anonymity: Counter = Counter()
        self.passing = 0
        self.recent: Deque[CheckResult] = deque(maxlen=8)
        self.start = time.perf_counter()
        self.speed: Deque[float] = deque(maxlen=60)
        self._sample_at = self.start
        self._sample_checked = 0

    @property
    def found(self) -> int:
        return sum(self.working_by_type.values())

    def add_checked(self, ptype: str) -> None:
        self.checked += 1
        self.checked_by_type[ptype] += 1

    def add_working(self, r: CheckResult) -> None:
        self.working_by_type[r.ptype] += 1
        self.latency_sum += r.latency
        self.fastest = r.latency if self.fastest is None else min(self.fastest, r.latency)
        self.latency_hist[sum(r.latency >= e for e in LATENCY_EDGES)] += 1
        self.recent.append(r)

    def add_details(self, r: CheckResult) -> None:
        if r.https:
            self.https_ok += 1
        if r.anonymity:
            self.anonymity[r.anonymity] += 1

    def sample_speed(self) -> float:
        now = time.perf_counter()
        if now - self._sample_at >= 1.0:
            self.speed.append((self.checked - self._sample_checked) / (now - self._sample_at))
            self._sample_at, self._sample_checked = now, self.checked
        return self.speed[-1] if self.speed else 0.0


class CheckDashboard:
    def __init__(self, stats: LiveStats, outfile: Path, concurrency: int, details: bool,
                 filters_text: str = "", want: int = 0):
        self.s = stats
        self.outfile = outfile
        self.concurrency = concurrency
        self.details = details
        self.filters_text = filters_text
        self.want = want
        self.progress = Progress(
            TextColumn("[bold]Fortschritt"),
            BarColumn(bar_width=None, complete_style=ACCENT, finished_style=GOOD),
            TaskProgressColumn(),
            CountColumn(),
            TextColumn("[grey50]· noch"),
            TimeRemainingColumn(),
            expand=True,
        )
        self.task = self.progress.add_task("", total=stats.total)

    def advance(self) -> None:
        self.progress.advance(self.task)

    def __rich__(self):
        s = self.s
        width = console.size.width
        speed = s.sample_speed()
        avg = s.checked / max(time.perf_counter() - s.start, 1e-6)
        found = s.found

        wide = width >= 100
        kpis = row(
            card("Geprüft", fmt(s.checked), f"von {fmt(s.total)}"),
            card("Gefunden", fmt(found), f"{pct(found, s.checked)} Treffer", f"bold {GOOD}"),
            card("Tempo", f"{fmt(speed or avg)}/s", sparkline(s.speed, max(width // 4 - 6, 8)), f"bold {ACCENT}"),
            card(
                "Ø Latenz", f"{s.latency_sum / found:,.0f} ms".replace(",", ".") if found else "–",
                f"min. {fmt(s.fastest)} ms" if s.fastest is not None else "noch keiner",
                f"bold {latency_style(s.latency_sum // found)}" if found else "bold",
            ),
        )

        panel_w = width * 4 // 11  # Protokolle/Latenz bekommen je 4 von 11 Anteilen
        bar_w = max(panel_w - 18, 4)
        proto = Table.grid(padding=(0, 1))
        proto.add_column()
        proto.add_column()
        proto.add_column(justify="right")
        for t in PROXY_TYPES:
            if s.total_by_type.get(t):
                proto.add_row(
                    type_badge(t),
                    bar(s.checked_by_type[t], s.total_by_type[t], bar_w, TYPE_STYLE[t]),
                    Text(fmt(s.working_by_type[t]), style=f"bold {GOOD}"),
                )

        hist_w = max(panel_w - 19, 4)
        hist = Table.grid(padding=(0, 1))
        hist.add_column(style=MUTED)
        hist.add_column()
        hist.add_column(justify="right")
        top = max(s.latency_hist) or 1
        colors = (GOOD, GOOD, GOOD, WARN, WARN, BAD)
        for label, n, color in zip(LATENCY_LABELS, s.latency_hist, colors):
            hist.add_row(label, bar(n, top, hist_w, color), fmt(n))

        side = Table.grid(padding=(0, 1))
        side.add_column()
        side.add_column(justify="right")
        if self.details:
            side.add_row(Text("✔ HTTPS", style=GOOD), fmt(s.https_ok))
            for level in ("elite", "anonymous", "transparent"):
                letter, style = ANON_STYLE[level]
                side.add_row(Text(f"{letter} {ANON_LABEL[level]}", style=style), fmt(s.anonymity[level]))
        for cc, n in s.countries.most_common(6 if not self.details else 2):
            side.add_row(country_cell(cc), fmt(n))
        if not side.row_count:
            side.add_row(Text("–", style=MUTED), "")

        height = len(LATENCY_LABELS) + 2  # alle drei gleich hoch
        middle = row(
            Panel(proto, title="Protokolle", title_align="left", subtitle="Balken = geprüft",
                  subtitle_align="left", box=box.ROUNDED, border_style=MUTED, height=height),
            Panel(hist, title="Latenz", title_align="left", box=box.ROUNDED, border_style=MUTED, height=height),
            Panel(side, title=("Details & Länder" if wide else "Details") if self.details else "Länder", title_align="left",
                  box=box.ROUNDED, border_style=MUTED, height=height),
            ratios=(4, 4, 3),
        )

        recent = table()
        recent.add_column("Typ", width=6)
        recent.add_column("Proxy", min_width=21, ratio=3, no_wrap=True)
        recent.add_column("Land", width=5)
        if self.details:
            recent.add_column("TLS", width=3, justify="center")
            recent.add_column("Anon", width=4, justify="center")
        if wide:
            recent.add_column("Exit-IP", ratio=2, style=MUTED, no_wrap=True)
        recent.add_column("Latenz", justify="right", width=8)
        for r in reversed(s.recent):
            cells = [type_badge(r.ptype), r.proxy, country_cell(r.country)]
            if self.details:
                cells += [https_cell(r.https), anon_cell(r.anonymity)]
            if wide:
                cells.append(r.exit_ip)
            cells.append(Text(f"{fmt(r.latency)} ms", style=latency_style(r.latency)))
            recent.add_row(*cells)

        footer = Text("  Strg+C beendet und speichert", style=MUTED)
        footer.append(f"  ·  {fmt(self.concurrency)} parallel", style=MUTED)
        if self.want:
            footer.append(f"  ·  Ziel {fmt(min(s.passing, self.want))} / {fmt(self.want)}", style=f"bold {ACCENT}")
        if self.filters_text:
            footer.append(f"\n  Filter: {self.filters_text}", style=WARN)
            footer.append(f"  ·  {fmt(s.passing)} passend", style=MUTED)
        footer.append(f"\n  → {self.outfile}", style=MUTED)
        if s.checked >= 2000 and found < s.checked * BLOCKED_HIT_RATE:
            footer.append("\n  ⚠ Kaum Treffer – blockiert dein Netz (Firewall) Proxy-Verbindungen?", style=f"bold {WARN}")

        return Group(
            header(2, s.start),
            kpis,
            middle,
            Panel(self.progress, box=box.ROUNDED, border_style=ACCENT, padding=(0, 1)),
            Panel(recent if s.recent else Align.center(Text("warte auf den ersten Treffer …", style=MUTED)),
                  title="Zuletzt gefunden", title_align="left", box=box.ROUNDED, border_style=GOOD),
            footer,
        )


# --------------------------------------------------------------------------- #
# Phase 4: Bericht
# --------------------------------------------------------------------------- #

def render_summary(
    stats: LiveStats,
    results: List[CheckResult],
    kept: List[CheckResult],
    best_sources: Iterable[Tuple[float, int, int, str]],
    files: Dict[str, Path],
    details: bool,
    filters_text: str,
) -> None:
    width = console.size.width
    wide = width >= 110
    elapsed = time.perf_counter() - stats.start
    found = stats.found
    console.print()
    console.print(header(3, stats.start))

    console.print(row(
        card("Funktionieren", fmt(found), f"{pct(found, stats.checked)} Treffer", f"bold {GOOD}"),
        card("Gespeichert", fmt(len(kept)), filters_text or "ohne Filter", f"bold {ACCENT}"),
        card("Dauer", fmt_duration(elapsed), f"{fmt(stats.checked / max(elapsed, 1e-6))} Prüf./s"),
        card(
            "Ø Latenz", f"{stats.latency_sum / found:,.0f} ms".replace(",", ".") if found else "–",
            f"min. {fmt(stats.fastest)} ms" if stats.fastest is not None else "",
            f"bold {latency_style(stats.latency_sum // found)}" if found else "bold",
        ),
    ))

    proto = table()
    proto.add_column("Typ")
    proto.add_column("OK", justify="right", style=GOOD)
    proto.add_column("geprüft", justify="right", style=MUTED)
    proto.add_column("Quote", justify="right")
    for t in PROXY_TYPES:
        if stats.total_by_type.get(t):
            proto.add_row(type_badge(t), fmt(stats.working_by_type[t]), fmt(stats.checked_by_type[t]),
                          pct(stats.working_by_type[t], stats.checked_by_type[t]))
    if details and found:
        proto.add_row("", "", "", "")
        proto.add_row(Text("✔ HTTPS", style=GOOD), fmt(stats.https_ok), "", pct(stats.https_ok, found))
        for level in ("elite", "anonymous", "transparent"):
            letter, style = ANON_STYLE[level]
            proto.add_row(Text(f"{letter} {ANON_LABEL[level]}", style=style), fmt(stats.anonymity[level]), "",
                          pct(stats.anonymity[level], found))

    # In breiten Terminals drei Spalten, sonst Protokolle oben und Länder/Latenz darunter
    bar_w = max((width // 3 if wide else width // 2) - 24, 4)
    lands = table()
    lands.add_column("Land")
    lands.add_column("Anzahl", justify="right")
    lands.add_column("")
    top_countries = stats.countries.most_common(len(LATENCY_LABELS))
    peak = top_countries[0][1] if top_countries else 1
    for cc, n in top_countries:
        lands.add_row(country_cell(cc), fmt(n), bar(n, peak, bar_w, ACCENT))
    if not top_countries:
        lands.add_row(Text("keine Länderdaten", style=MUTED), "", "")

    hist = table()
    hist.add_column("Latenz")
    hist.add_column("Anzahl", justify="right")
    hist.add_column("")
    peak_l = max(stats.latency_hist) or 1
    for label, n, color in zip(LATENCY_LABELS, stats.latency_hist, (GOOD, GOOD, GOOD, WARN, WARN, BAD)):
        hist.add_row(label, fmt(n), bar(n, peak_l, bar_w, color))

    if wide:
        console.print(row(panel(proto, "Protokolle"), panel(lands, "Länder"), panel(hist, "Latenz")))
    else:
        console.print(panel(proto, "Protokolle"))
        console.print(row(panel(lands, "Länder"), panel(hist, "Latenz")))

    if kept:
        fastest = table()
        fastest.add_column("#", justify="right", style=MUTED, width=3)
        fastest.add_column("Proxy", ratio=3, no_wrap=True)
        fastest.add_column("Land", width=5)
        if details:
            fastest.add_column("TLS", width=3, justify="center")
            fastest.add_column("Anon", width=4, justify="center")
        fastest.add_column("Latenz", justify="right", width=8)
        for n, r in enumerate(sorted(kept, key=lambda r: r.latency)[:10], 1):
            cells = [str(n), Text.assemble((f"{r.ptype}://", TYPE_STYLE[r.ptype]), r.proxy), country_cell(r.country)]
            if details:
                cells += [https_cell(r.https), anon_cell(r.anonymity)]
            cells.append(Text(f"{fmt(r.latency)} ms", style=latency_style(r.latency)))
            fastest.add_row(*cells)
        console.print(panel(fastest, "Die 10 schnellsten", GOOD))

    best = list(best_sources)
    if best:
        src = table()
        src.add_column("Quelle", ratio=1, no_wrap=True, overflow="ellipsis")
        src.add_column("Treffer", justify="right", style=GOOD)
        src.add_column("OK / geprüft", justify="right", style=MUTED)
        for rate, w, c, url in best:
            src.add_row(short_url(url), f"{rate * 100:.1f} %".replace(".", ","), f"{fmt(w)} / {fmt(c)}")
        console.print(panel(src, "Beste Quellen dieses Laufs"))

    if files:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold", no_wrap=True)
        grid.add_column(overflow="fold")
        for label, path in files.items():
            grid.add_row(label, Text(_display_path(path), style=ACCENT))
        console.print(panel(grid, "Dateien", ACCENT))


def _display_path(path: Path) -> str:
    """Relativ zum aktuellen Ordner, wenn möglich – kürzer und klickbar."""
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def render_source_ranking(rows: List[Tuple[str, object, str]], total_known: int, reasons: Counter) -> None:
    ranking = table()
    ranking.add_column("#", justify="right", style=MUTED)
    ranking.add_column("Quelle", no_wrap=True, overflow="ellipsis", ratio=1)
    ranking.add_column("Treffer", justify="right")
    ranking.add_column("", width=10)
    ranking.add_column("geprüft", justify="right", style=MUTED)
    ranking.add_column("Einträge", justify="right", style=MUTED)
    ranking.add_column("Status")
    best = max((r.working / r.checked for _, r, _ in rows if r.checked), default=1) or 1
    for n, (url, rec, status) in enumerate(rows, 1):
        rate = rec.working / rec.checked if rec.checked else 0
        ranking.add_row(
            str(n), short_url(url), f"{rate * 100:.1f} %".replace(".", ","), bar(rate, best, 10, GOOD),
            fmt(rec.checked), fmt(rec.count),
            Text(status, style=GOOD if status == "aktiv" else BAD),
        )
    console.print(panel(ranking, f"Quellen nach Trefferquote · {len(rows)} bewertet, {fmt(total_known)} bekannt", ACCENT))
    if not rows:
        note("Noch keine Bewertungen – Trefferquoten gibt es erst nach einem Prüflauf.", MUTED, "ℹ")
    console.print(Text("  Status aller Quellen: ", style=MUTED) + Text(
        ", ".join(f"{n} {r}" for r, n in reasons.most_common())))


def centered(text: str, style: str = MUTED) -> Align:
    return Align.center(Text(text, style=style))
