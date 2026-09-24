"""Abschlussbericht nach einem Lauf und Quellen-Rangliste."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from rich.table import Table
from rich.text import Text

from ..checker import CheckResult
from ..parsing import PROXY_TYPES
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
    table,
    type_badge,
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
    width = widgets.console.size.width
    wide = width >= 110
    elapsed = time.perf_counter() - stats.start
    found = stats.found
    widgets.console.print()
    widgets.console.print(header(3, stats.start))

    widgets.console.print(row(
        card("Funktionieren", fmt(found), hit_line(found, stats.checked, stats.fakes), f"bold {GOOD}"),
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
        widgets.console.print(row(panel(proto, "Protokolle"), panel(lands, "Länder"), panel(hist, "Latenz")))
    else:
        widgets.console.print(panel(proto, "Protokolle"))
        widgets.console.print(row(panel(lands, "Länder"), panel(hist, "Latenz")))

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
        widgets.console.print(panel(fastest, "Die 10 schnellsten", GOOD))

    best = list(best_sources)
    if best:
        src = table()
        src.add_column("Quelle", ratio=1, no_wrap=True, overflow="ellipsis")
        src.add_column("Treffer", justify="right", style=GOOD)
        src.add_column("OK / geprüft", justify="right", style=MUTED)
        for rate, w, c, url in best:
            src.add_row(short_url(url), f"{rate * 100:.1f} %".replace(".", ","), f"{fmt(w)} / {fmt(c)}")
        widgets.console.print(panel(src, "Beste Quellen dieses Laufs"))

    if files:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold", no_wrap=True)
        grid.add_column(overflow="fold")
        for label, path in files.items():
            grid.add_row(label, Text(_display_path(path), style=ACCENT))
        widgets.console.print(panel(grid, "Dateien", ACCENT))


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
    title = f"Quellen nach Trefferquote · {len(rows)} bewertet, {fmt(total_known)} bekannt"
    widgets.console.print(panel(ranking, title, ACCENT))
    if not rows:
        note("Noch keine Bewertungen – Trefferquoten gibt es erst nach einem Prüflauf.", MUTED, "ℹ")
    widgets.console.print(Text("  Status aller Quellen: ", style=MUTED) + Text(
        ", ".join(f"{n} {r}" for r, n in reasons.most_common())))
