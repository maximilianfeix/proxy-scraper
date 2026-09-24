"""Live-Ansichten während des Sammelns und Prüfens."""

from __future__ import annotations

import time
from collections import Counter, deque
from pathlib import Path
from typing import Deque, Dict, Optional, Sequence

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from ..checker import CheckResult
from ..parsing import PROXY_TYPES
from ..targets import target_label
from . import widgets
from .widgets import (
    ACCENT,
    ANON_LABEL,
    ANON_STYLE,
    BAD,
    BLOCKED_HIT_RATE,
    BORDER,
    GOOD,
    LATENCY_EDGES,
    LATENCY_LABELS,
    MUTED,
    TYPE_STYLE,
    WARN,
    CountColumn,
    anon_cell,
    bar,
    card,
    country_cell,
    fmt,
    header,
    https_cell,
    latency_style,
    panel_title,
    pct,
    row,
    sparkline,
    table,
    type_badge,
)

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
            card("Geladen", f"{self.bytes / 2**20:,.0f} MB".replace(",", "."),
                 f"{self.bytes / 2**20 / elapsed:.1f} MB/s"),
            card("Proxys", fmt(self.unique), "einzigartig", f"bold {ACCENT}"),
        )
        return Group(
            header(1, self.started),
            Panel(Group(self.progress, stats), box=box.ROUNDED, border_style=ACCENT,
                  title=panel_title("Sammeln", ACCENT), title_align="left"),
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
        self.fakes = 0  # bestanden die Basisprüfung, aber nicht die Bestätigung
        self.details_saved = 0  # HTTPS-Tests, die dank Filter entfallen konnten
        self.targets_ok: Counter = Counter()  # Zielseiten-URL -> Anzahl Proxys, die sie erreichen
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
        """Bestätigter Treffer – die Anonymität ist ab hier bekannt."""
        if r.anonymity:
            self.anonymity[r.anonymity] += 1
        self.working_by_type[r.ptype] += 1
        self.latency_sum += r.latency
        self.fastest = r.latency if self.fastest is None else min(self.fastest, r.latency)
        self.latency_hist[sum(r.latency >= e for e in LATENCY_EDGES)] += 1
        self.recent.append(r)

    def add_details(self, r: CheckResult) -> None:
        if r.https:
            self.https_ok += 1
        for url, ok in r.targets.items():
            # auch 0 zählen: eine Zielseite, die kein Proxy erreicht, soll im Bericht sichtbar bleiben
            self.targets_ok[url] += int(ok)

    def sample_speed(self) -> float:
        now = time.perf_counter()
        if now - self._sample_at >= 1.0:
            self.speed.append((self.checked - self._sample_checked) / (now - self._sample_at))
            self._sample_at, self._sample_checked = now, self.checked
        return self.speed[-1] if self.speed else 0.0


def hit_line(found: int, checked: int, fakes: int) -> Text:
    """"1,5 % Treffer" – mit aussortierten Fake-Proxys kurz genug für schmale Karten: "1,5 % · 638 Fakes"."""
    if not fakes:
        return Text(f"{pct(found, checked)} Treffer", style=MUTED)
    return Text.assemble((f"{pct(found, checked)} · ", MUTED), (f"{fmt(fakes)} Fakes", WARN))


class CheckDashboard:
    def __init__(self, stats: LiveStats, outfile: Path, concurrency: int, details: bool,
                 filters_text: str = "", want: int = 0, targets: Sequence[str] = ()):
        self.s = stats
        self.targets = list(targets)
        self.outfile = outfile
        self.concurrency = concurrency
        self.details = details
        self.filters_text = filters_text
        self.want = want
        self.progress = Progress(
            TextColumn("[bold]Fortschritt"),
            BarColumn(bar_width=None, complete_style=ACCENT, finished_style=GOOD),
            TaskProgressColumn(text_format=f"[bold {ACCENT}]{{task.percentage:>3.0f}}%"),
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
        width = widgets.console.size.width
        speed = s.sample_speed()
        avg = s.checked / max(time.perf_counter() - s.start, 1e-6)
        found = s.found

        wide = width >= 100
        kpis = row(
            card("Geprüft", fmt(s.checked), f"von {fmt(s.total)}"),
            card("Gefunden", fmt(found), hit_line(found, s.checked, s.fakes), f"bold {GOOD}"),
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
        for url in self.targets:
            side.add_row(Text(f"🎯 {target_label(url, self.targets)}", style=ACCENT, overflow="ellipsis", no_wrap=True),
                         fmt(s.targets_ok[url]))
        for level in ("elite", "anonymous", "transparent"):
            letter, style = ANON_STYLE[level]
            side.add_row(Text(f"{letter} {ANON_LABEL[level]}", style=style), fmt(s.anonymity[level]))
        if s.details_saved:
            side.add_row(Text("⏭ gespart", style=MUTED), fmt(s.details_saved))
        for cc, n in s.countries.most_common(max(len(LATENCY_LABELS) - side.row_count, 0)):
            side.add_row(country_cell(cc), fmt(n))
        if not side.row_count:
            side.add_row(Text("–", style=MUTED), "")

        height = len(LATENCY_LABELS) + 2  # alle drei gleich hoch
        middle = row(
            Panel(proto, title=panel_title("Protokolle"), title_align="left",
                  subtitle=Text(" Balken = geprüft ", style=MUTED),
                  subtitle_align="left", box=box.ROUNDED, border_style=BORDER, height=height),
            Panel(hist, title=panel_title("Latenz"), title_align="left", box=box.ROUNDED, border_style=BORDER,
                  height=height),
            Panel(side, title=panel_title("Details & Länder" if wide else "Details"),
                  title_align="left", box=box.ROUNDED, border_style=BORDER, height=height),
            ratios=(4, 4, 3),
        )

        recent = table()
        recent.add_column("Typ", width=6)
        recent.add_column("Proxy", min_width=21, ratio=3, no_wrap=True)
        recent.add_column("Land", width=5)
        if self.details:
            recent.add_column("TLS", width=3, justify="center")
        if self.targets:
            recent.add_column("Ziel", width=4, justify="center")
        recent.add_column("Anon", width=4, justify="center")
        if wide:
            recent.add_column("Exit-IP", ratio=2, style=MUTED, no_wrap=True)
        recent.add_column("Latenz", justify="right", width=8)
        for r in reversed(s.recent):
            cells = [type_badge(r.ptype), r.proxy, country_cell(r.country)]
            if self.details:
                cells.append(https_cell(r.https))
            if self.targets:
                cells.append(https_cell(all(r.targets.get(u) for u in self.targets) if r.targets else None))
            cells.append(anon_cell(r.anonymity))
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
        if s.checked >= 2000 and found + s.fakes < s.checked * BLOCKED_HIT_RATE:
            footer.append("\n  ⚠ Kaum Treffer – blockiert dein Netz (Firewall) Proxy-Verbindungen?",
                          style=f"bold {WARN}")

        return Group(
            header(2, s.start),
            kpis,
            middle,
            Panel(self.progress, box=box.ROUNDED, border_style=ACCENT, padding=(0, 1)),
            Panel(recent if s.recent else Align.center(Text("warte auf den ersten Treffer …", style=MUTED)),
                  title=panel_title("Zuletzt gefunden", GOOD), title_align="left", box=box.ROUNDED, border_style=GOOD),
            footer,
        )
