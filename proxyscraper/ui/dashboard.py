"""Live views while collecting and checking."""

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
    shown_proxy,
    sparkline,
    table,
    type_badge,
)

# --------------------------------------------------------------------------- #
# Phase 2: collecting
# --------------------------------------------------------------------------- #


class CollectView:
    def __init__(self, total_sources: int, started: float):
        self.started = started
        self.ok = 0
        self.failed = 0
        self.bytes = 0
        self.cached = 0  # lists that were unchanged per ETag
        self.unique = 0
        self.progress = Progress(
            SpinnerColumn(style=ACCENT),
            TextColumn("[bold]Loading & parsing sources"),
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
            card("Sources OK", fmt(self.ok), f"{fmt(self.failed)} failed", f"bold {GOOD}"),
            card("Loaded", f"{self.bytes / 2**20:,.0f} MB",
                 f"{self.bytes / 2**20 / elapsed:.1f} MB/s"
                 + (f" · {fmt(self.cached)} from cache" if self.cached else "")),
            card("Proxies", fmt(self.unique), "unique", f"bold {ACCENT}"),
        )
        return Group(
            header(1, self.started),
            Panel(Group(self.progress, stats), box=box.ROUNDED, border_style=ACCENT,
                  title=panel_title("Collecting", ACCENT), title_align="left"),
        )


# --------------------------------------------------------------------------- #
# Phase 3: checking
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
        self.fakes = 0  # passed the basic check, but not the confirmation
        self.tampered = 0  # confirmed, but modified a known page (scripts, ads)
        self.hosting = 0  # hits that (probably) exit from a datacenter
        self.blocklisted = 0  # hits whose exit IP is on the SpamCop blocklist
        self.details_saved = 0  # HTTPS tests that could be skipped thanks to filters
        self.targets_ok: Counter = Counter()  # target site URL -> number of proxies that reach it
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
        """Confirmed hit – the anonymity is known from here on."""
        if r.anonymity:
            self.anonymity[r.anonymity] += 1
        if r.hosting:
            self.hosting += 1
        if r.blocklisted:
            self.blocklisted += 1
        self.working_by_type[r.ptype] += 1
        self.latency_sum += r.latency
        self.fastest = r.latency if self.fastest is None else min(self.fastest, r.latency)
        self.latency_hist[sum(r.latency >= e for e in LATENCY_EDGES)] += 1
        self.recent.append(r)

    def add_details(self, r: CheckResult) -> None:
        if r.https:
            self.https_ok += 1
        for url, ok in r.targets.items():
            # count 0 too: a target site that no proxy reaches should stay visible in the report
            self.targets_ok[url] += int(ok)

    def sample_speed(self) -> float:
        now = time.perf_counter()
        if now - self._sample_at >= 1.0:
            self.speed.append((self.checked - self._sample_checked) / (now - self._sample_at))
            self._sample_at, self._sample_checked = now, self.checked
        return self.speed[-1] if self.speed else 0.0


def hit_line(found: int, checked: int, fakes: int) -> Text:
    """"1.5% hits" – with filtered fake proxies short enough for narrow cards: "1.5% · 638 fakes"."""
    if not fakes:
        return Text(f"{pct(found, checked)} hits", style=MUTED)
    return Text.assemble((f"{pct(found, checked)} · ", MUTED), (f"{fmt(fakes)} fakes", WARN))


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
        self.judge = ""
        self.judge_note = ""
        self.rechecks = 0
        self.progress = Progress(
            TextColumn("[bold]Progress"),
            BarColumn(bar_width=None, complete_style=ACCENT, finished_style=GOOD),
            TaskProgressColumn(text_format=f"[bold {ACCENT}]{{task.percentage:>3.0f}}%"),
            CountColumn(),
            TextColumn(f"[{MUTED}]· left"),
            TimeRemainingColumn(),
            expand=True,
        )
        self.task = self.progress.add_task("", total=stats.total)

    def advance(self) -> None:
        self.progress.advance(self.task)

    def judge_changed(self, host: str) -> None:
        """The check target went down and was switched."""
        self.judge = host
        self.judge_note = f"check target switched → {host}"

    def add_rechecks(self, keys: Sequence[str]) -> None:
        """Proxies that get checked again because of an outage – they add to the total."""
        for key in keys:
            self.s.total_by_type[key.split(" ", 1)[0]] += 1
        self.rechecks += len(keys)
        self.s.total += len(keys)
        self.progress.update(self.task, total=self.s.total)

    def __rich__(self):
        s = self.s
        width = widgets.console.size.width
        speed = s.sample_speed()
        avg = s.checked / max(time.perf_counter() - s.start, 1e-6)
        found = s.found

        wide = width >= 100
        kpis = row(
            card("Checked", fmt(s.checked), f"of {fmt(s.total)}"),
            card("Found", fmt(found), hit_line(found, s.checked, s.fakes), f"bold {GOOD}"),
            card("Speed", f"{fmt(speed or avg)}/s", sparkline(s.speed, max(width // 4 - 6, 8)), f"bold {ACCENT}"),
            card(
                "Ø latency", f"{s.latency_sum / found:,.0f} ms" if found else "–",
                f"min. {fmt(s.fastest)} ms" if s.fastest is not None else "none yet",
                f"bold {latency_style(s.latency_sum // found)}" if found else "bold",
            ),
        )

        panel_w = width * 4 // 11  # protocols/latency get 4 of 11 shares each
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
        if s.hosting:
            side.add_row(Text("▣ datacenter", style=MUTED), fmt(s.hosting))
        if s.blocklisted:
            side.add_row(Text("⊘ blocklisted", style=MUTED), fmt(s.blocklisted))
        if s.details_saved:
            side.add_row(Text("⏭ skipped", style=MUTED), fmt(s.details_saved))
        for cc, n in s.countries.most_common(max(len(LATENCY_LABELS) - side.row_count, 0)):
            side.add_row(country_cell(cc), fmt(n))
        if not side.row_count:
            side.add_row(Text("–", style=MUTED), "")

        height = len(LATENCY_LABELS) + 2  # all three the same height
        middle = row(
            Panel(proto, title=panel_title("Protocols"), title_align="left",
                  subtitle=Text(" bar = checked ", style=MUTED),
                  subtitle_align="left", box=box.ROUNDED, border_style=BORDER, height=height),
            Panel(hist, title=panel_title("Latency"), title_align="left", box=box.ROUNDED, border_style=BORDER,
                  height=height),
            Panel(side, title=panel_title("Details & countries" if wide else "Details"),
                  title_align="left", box=box.ROUNDED, border_style=BORDER, height=height),
            ratios=(4, 4, 3),
        )

        recent = table()
        recent.add_column("Type", width=6)
        recent.add_column("Proxy", min_width=21, ratio=3, no_wrap=True)
        recent.add_column("Ctry", width=5)
        if self.details:
            recent.add_column("TLS", width=3, justify="center")
        if self.targets:
            recent.add_column("Site", width=4, justify="center")
        recent.add_column("Anon", width=4, justify="center")
        if wide:
            recent.add_column("Exit-IP", ratio=2, style=MUTED, no_wrap=True)
        recent.add_column("Latency", justify="right", width=8)
        for r in reversed(s.recent):
            cells = [type_badge(r.ptype), shown_proxy(r.proxy), country_cell(r.country)]
            if self.details:
                cells.append(https_cell(r.https))
            if self.targets:
                cells.append(https_cell(all(r.targets.get(u) for u in self.targets) if r.targets else None))
            cells.append(anon_cell(r.anonymity))
            if wide:
                cells.append(r.exit_ip)
            cells.append(Text(f"{fmt(r.latency)} ms", style=latency_style(r.latency)))
            recent.add_row(*cells)

        footer = Text("  Ctrl+C stops and saves", style=MUTED)
        footer.append(f"  ·  {fmt(self.concurrency)} parallel", style=MUTED)
        if s.tampered:
            footer.append(f"  ·  {fmt(s.tampered)} dropped for tampering", style=WARN)
        if self.judge:
            footer.append(f"  ·  target {self.judge}", style=MUTED)
        if self.judge_note:
            footer.append(f"\n  ⚠ {self.judge_note}, {fmt(self.rechecks)} proxies are checked again", style=WARN)
        if self.want:
            footer.append(f"  ·  goal {fmt(min(s.passing, self.want))} / {fmt(self.want)}", style=f"bold {ACCENT}")
        if self.filters_text:
            footer.append(f"\n  Filter: {self.filters_text}", style=WARN)
            footer.append(f"  ·  {fmt(s.passing)} matching", style=MUTED)
        footer.append(f"\n  → {self.outfile}", style=MUTED)
        if s.checked >= 2000 and found + s.fakes + s.tampered < s.checked * BLOCKED_HIT_RATE:
            footer.append("\n  ⚠ Hardly any hits – is your network (firewall) blocking proxy connections?",
                          style=f"bold {WARN}")

        return Group(
            header(2, s.start),
            kpis,
            middle,
            Panel(self.progress, box=box.ROUNDED, border_style=ACCENT, padding=(0, 1)),
            Panel(recent if s.recent else Align.center(Text("waiting for the first hit …", style=MUTED)),
                  title=panel_title("Found recently", GOOD), title_align="left", box=box.ROUNDED, border_style=GOOD),
            footer,
        )
