"""Final report after a run and the source ranking."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from rich.table import Table
from rich.text import Text

from ..checker import CheckResult
from ..parsing import PROXY_TYPES
from ..targets import target_label
from . import widgets
from .dashboard import LiveStats, hit_line
from .widgets import (
    ACCENT,
    ANON_LABEL,
    ANON_STYLE,
    BAD,
    GOOD,
    LATENCY_LABELS,
    MUTED,
    TYPE_STYLE,
    WARN,
    anon_cell,
    bar,
    card,
    country_cell,
    fmt,
    fmt_duration,
    header,
    https_cell,
    latency_style,
    note,
    panel,
    pct,
    row,
    short_url,
    shown_proxy,
    table,
    type_badge,
)

# --------------------------------------------------------------------------- #
# Phase 4: report
# --------------------------------------------------------------------------- #


def render_summary(
    stats: LiveStats,
    results: List[CheckResult],
    kept: List[CheckResult],
    best_sources: Iterable[Tuple[float, int, int, str]],
    files: Dict[str, Path],
    details: bool,
    filters_text: str,
    next_steps: Sequence[Tuple[str, str]] = (),
) -> None:
    width = widgets.console.size.width
    wide = width >= 110
    elapsed = time.perf_counter() - stats.start
    found = stats.found
    widgets.console.print()
    widgets.console.print(header(3, stats.start))

    widgets.console.print(row(
        card("Working", fmt(found), hit_line(found, stats.checked, stats.fakes), f"bold {GOOD}"),
        card("Saved", fmt(len(kept)), filters_text or "no filters", f"bold {ACCENT}"),
        card("Duration", fmt_duration(elapsed), f"{fmt(stats.checked / max(elapsed, 1e-6))} checks/s"),
        card(
            "Ø latency", f"{stats.latency_sum / found:,.0f} ms" if found else "–",
            f"min. {fmt(stats.fastest)} ms" if stats.fastest is not None else "",
            f"bold {latency_style(stats.latency_sum // found)}" if found else "bold",
        ),
    ))

    proto = table()
    proto.add_column("Type", no_wrap=True, min_width=16)
    proto.add_column("OK", justify="right", style=GOOD)
    proto.add_column("checked", justify="right", style=MUTED)
    proto.add_column("Rate", justify="right")
    for t in PROXY_TYPES:
        if stats.total_by_type.get(t):
            proto.add_row(type_badge(t), fmt(stats.working_by_type[t]), fmt(stats.checked_by_type[t]),
                          pct(stats.working_by_type[t], stats.checked_by_type[t]))
    if found:
        proto.add_row("", "", "", "")
        if details:
            proto.add_row(Text("✔ HTTPS", style=GOOD), fmt(stats.https_ok), "", pct(stats.https_ok, found))
        for url, ok in sorted(stats.targets_ok.items(), key=lambda kv: -kv[1]):
            label = target_label(url, stats.targets_ok)
            proto.add_row(Text(f"🎯 {label}", style=ACCENT), fmt(ok), "", pct(ok, found))
        for level in ("elite", "anonymous", "transparent"):
            letter, style = ANON_STYLE[level]
            proto.add_row(Text(f"{letter} {ANON_LABEL[level]}", style=style), fmt(stats.anonymity[level]), "",
                          pct(stats.anonymity[level], found))
        if stats.hosting:
            proto.add_row(Text("▣ Datacenter", style=MUTED), fmt(stats.hosting), "", pct(stats.hosting, found))
        if stats.blocklisted:
            proto.add_row(Text("⊘ Blocklisted", style=MUTED), fmt(stats.blocklisted), "", pct(stats.blocklisted, found))
        if stats.details_saved:
            proto.add_row(Text("⏭ HTTPS tests skipped", style=MUTED), fmt(stats.details_saved), "", "")

    # three columns in wide terminals, otherwise protocols on top and countries/latency below
    bar_w = max((width // 3 if wide else width // 2) - 24, 4)
    lands = table()
    lands.add_column("Country")
    lands.add_column("Count", justify="right")
    lands.add_column("")
    top_countries = stats.countries.most_common(len(LATENCY_LABELS))
    peak = top_countries[0][1] if top_countries else 1
    for cc, n in top_countries:
        lands.add_row(country_cell(cc), fmt(n), bar(n, peak, bar_w, ACCENT))
    if not top_countries:
        lands.add_row(Text("no country data", style=MUTED), "", "")

    hist = table()
    hist.add_column("Latency")
    hist.add_column("Count", justify="right")
    hist.add_column("")
    peak_l = max(stats.latency_hist) or 1
    for label, n, color in zip(LATENCY_LABELS, stats.latency_hist, (GOOD, GOOD, GOOD, WARN, WARN, BAD)):
        hist.add_row(label, fmt(n), bar(n, peak_l, bar_w, color))

    if wide:
        widgets.console.print(row(panel(proto, "Protocols"), panel(lands, "Countries"), panel(hist, "Latency")))
    else:
        widgets.console.print(panel(proto, "Protocols"))
        widgets.console.print(row(panel(lands, "Countries"), panel(hist, "Latency")))

    if kept:
        fastest = table()
        fastest.add_column("#", justify="right", style=MUTED, width=3)
        fastest.add_column("Proxy", ratio=3, no_wrap=True)
        fastest.add_column("Ctry", width=5)
        if details:
            fastest.add_column("TLS", width=3, justify="center")
            fastest.add_column("Anon", width=4, justify="center")
        fastest.add_column("Latency", justify="right", width=8)
        for n, r in enumerate(sorted(kept, key=lambda r: r.latency)[:10], 1):
            url = Text.assemble((f"{r.ptype}://", TYPE_STYLE[r.ptype]), shown_proxy(r.proxy))
            cells = [str(n), url, country_cell(r.country)]
            if details:
                cells += [https_cell(r.https), anon_cell(r.anonymity)]
            cells.append(Text(f"{fmt(r.latency)} ms", style=latency_style(r.latency)))
            fastest.add_row(*cells)
        widgets.console.print(panel(fastest, "The 10 fastest", GOOD))

    best = list(best_sources)
    if best:
        src = table()
        src.add_column("Source", ratio=1, no_wrap=True, overflow="ellipsis")
        src.add_column("Hit rate", justify="right", style=GOOD)
        src.add_column("OK / checked", justify="right", style=MUTED)
        for rate, w, c, url in best:
            src.add_row(short_url(url), f"{rate * 100:.1f}%", f"{fmt(w)} / {fmt(c)}")
        widgets.console.print(panel(src, "Best sources of this run"))

    if files:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold", no_wrap=True)
        grid.add_column(overflow="fold")
        for label, path in files.items():
            grid.add_row(label, Text(_display_path(path), style=ACCENT))
        widgets.console.print(panel(grid, "Files", ACCENT))

    if next_steps:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=MUTED, no_wrap=True)
        grid.add_column(overflow="fold")
        for label, command in next_steps:
            grid.add_row(label, Text("$ ", style=MUTED) + Text(command, style="bold"))
        widgets.console.print(panel(grid, "Next steps", GOOD))


def _display_path(path: Path) -> str:
    """Relative to the current folder if possible – shorter and clickable."""
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def render_source_ranking(rows: List[Tuple[str, object, str]], total_known: int, reasons: Counter) -> None:
    ranking = table()
    ranking.add_column("#", justify="right", style=MUTED)
    ranking.add_column("Source", no_wrap=True, overflow="ellipsis", ratio=1)
    ranking.add_column("Hit rate", justify="right")
    ranking.add_column("", width=10)
    ranking.add_column("checked", justify="right", style=MUTED)
    ranking.add_column("Entries", justify="right", style=MUTED)
    ranking.add_column("Status")
    best = max((r.working / r.checked for _, r, _ in rows if r.checked), default=1) or 1
    for n, (url, rec, status) in enumerate(rows, 1):
        rate = rec.working / rec.checked if rec.checked else 0
        ranking.add_row(
            str(n), short_url(url), f"{rate * 100:.1f}%", bar(rate, best, 10, GOOD),
            fmt(rec.checked), fmt(rec.count),
            Text(status, style=GOOD if status == "active" else BAD),
        )
    title = f"Sources by hit rate · {len(rows)} rated, {fmt(total_known)} known"
    widgets.console.print(panel(ranking, title, ACCENT))
    if not rows:
        note("No ratings yet – hit rates only exist after a checking run.", MUTED, "ℹ")
    widgets.console.print(Text("  Status of all sources: ", style=MUTED) + Text(
        ", ".join(f"{n} {r}" for r, n in reasons.most_common())))
