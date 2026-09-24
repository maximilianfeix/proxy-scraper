"""Live-Ansicht des rotierenden Proxy-Servers (--serve)."""

from __future__ import annotations

import time

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..server import RotatingServer
from . import widgets
from .widgets import (
    ACCENT,
    BAD,
    GOOD,
    MUTED,
    TYPE_STYLE,
    WARN,
    card,
    fmt,
    fmt_duration,
    pct,
    row,
    shown_proxy,
    table,
)


def _mb(n: int) -> str:
    return f"{n / 2**20:.1f} MB".replace(".", ",")


class ServeDashboard:
    def __init__(self, server: RotatingServer):
        self.server = server

    def __rich__(self):
        server, st, pool = self.server, self.server.stats, self.server.pool
        address = f"{server.host}:{server.port}"
        width = widgets.console.size.width
        uptime = max(time.perf_counter() - st.started, 1e-6)
        usable = pool.usable

        title = Table.grid(expand=True)
        title.add_column()
        title.add_column(justify="right")
        title.add_row(
            Text.assemble(("● ", f"bold {GOOD}"), ("Proxy-Server läuft auf ", "bold"), (address, f"bold {ACCENT}")),
            Text(f"⏱ {fmt_duration(uptime)}", style=MUTED),
        )

        usage = Table.grid(padding=(0, 2))
        usage.add_column(style=MUTED, no_wrap=True)
        usage.add_column(overflow="fold")
        usage.add_row("Testen", Text(f"curl -x http://{address} https://api.ipify.org", style="bold"))
        usage.add_row("Terminal", Text(f"export http_proxy=http://{address} https_proxy=http://{address}"))
        usage.add_row("Browser/System", Text(f"HTTP-Proxy {server.host}, Port {server.port} (gilt auch für HTTPS)"))

        cards = row(
            card("Anfragen", fmt(st.requests), f"{st.requests / uptime * 60:.1f} pro Minute".replace(".", ",")),
            card("Erfolgreich", pct(st.ok, st.requests) if st.requests else "–",
                 f"{fmt(st.failed)} fehlgeschlagen", f"bold {GOOD}" if not st.failed else f"bold {WARN}"),
            card("Aktiv", fmt(st.active), "offene Verbindungen", f"bold {ACCENT}"),
            card("Pool", f"{fmt(len(usable))} / {fmt(len(pool.entries))}",
                 f"{fmt(len(pool.tls_capable))} für HTTPS · {fmt(len(pool.entries) - len(usable))} raus"),
            card("Traffic", _mb(st.bytes_down), f"↑ {_mb(st.bytes_up)}"),
        )

        recent = table()
        recent.add_column("", width=1)
        recent.add_column("Ziel", ratio=2, no_wrap=True, overflow="ellipsis")
        recent.add_column("über Proxy", ratio=2, no_wrap=True, overflow="ellipsis")
        if width >= 100:
            recent.add_column("Client", style=MUTED, no_wrap=True)
        recent.add_column("Versuche", justify="right", width=8)
        recent.add_column("Dauer", justify="right", width=8)
        for log in reversed(st.recent):
            ptype = log.via.split("://", 1)[0]
            cells = [
                Text("✔", style=GOOD) if log.ok else Text("✘", style=BAD),
                log.target,
                Text(log.via, style=TYPE_STYLE.get(ptype, MUTED)),
            ]
            if width >= 100:
                cells.append(log.client)
            cells += [str(log.attempts), f"{fmt(log.ms)} ms"]
            recent.add_row(*cells)

        busiest = table()
        busiest.add_column("Proxy", no_wrap=True, overflow="ellipsis")
        busiest.add_column("OK", justify="right", style=GOOD)
        busiest.add_column("Fehler", justify="right", style=MUTED)
        busiest.add_column("Latenz", justify="right")
        for entry in sorted(pool.entries, key=lambda e: (-e.ok, e.result.latency))[:5]:
            r = entry.result
            style = MUTED if entry.disabled else TYPE_STYLE.get(r.ptype, "")
            name = Text(f"{r.ptype}://{shown_proxy(r.proxy)}", style=style)
            busiest.add_row(name, fmt(entry.ok), fmt(entry.fail), f"{fmt(r.latency)} ms")

        waiting = Align.center(Text("warte auf die erste Verbindung …", style=MUTED))
        return Group(
            Panel(Group(title, Text(""), usage), box=box.HEAVY, border_style=ACCENT, padding=(0, 1)),
            cards,
            row(
                widgets.panel(recent if st.recent else waiting, "Letzte Verbindungen", GOOD),
                widgets.panel(busiest, "Meistgenutzte Proxys"),
                ratios=(3, 2),
            ),
            Text("  Strg+C beendet den Server · nur von diesem Rechner erreichbar", style=MUTED),
        )
