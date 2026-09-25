"""Live view of the rotating proxy server (--serve)."""

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
    return f"{n / 2**20:.1f} MB"


class ServeDashboard:
    def __init__(self, server: RotatingServer):
        self.server = server

    def __rich__(self):
        server, st, pool = self.server, self.server.stats, self.server.pool
        # if it listens on all addresses (Docker), it can still be reached locally via 127.0.0.1
        shown_host = {"0.0.0.0": "127.0.0.1", "": "127.0.0.1", "::": "[::1]"}.get(server.host, server.host)
        if ":" in shown_host and not shown_host.startswith("["):
            shown_host = f"[{shown_host}]"  # IPv6 in URLs only in brackets
        address = f"{shown_host}:{server.port}"
        width = widgets.console.size.width
        uptime = max(time.perf_counter() - st.started, 1e-6)
        usable = pool.usable

        title = Table.grid(expand=True)
        title.add_column()
        title.add_column(justify="right")
        title.add_row(
            Text.assemble(("● ", f"bold {GOOD}"), ("Proxy server running on ", "bold"), (address, f"bold {ACCENT}")),
            Text(f"⏱ {fmt_duration(uptime)}", style=MUTED),
        )

        usage = Table.grid(padding=(0, 2))
        usage.add_column(style=MUTED, no_wrap=True)
        usage.add_column(overflow="fold")
        usage.add_row("Test", Text(f"curl -x http://{address} https://api.ipify.org", style="bold"))
        usage.add_row("SOCKS5", Text(f"curl -x socks5h://{address} https://api.ipify.org"))
        usage.add_row("One country", Text(f"curl -x http://country-de:x@{address} https://api.ipify.org"))
        usage.add_row("Fixed session", Text(f"curl -x http://session-abc:x@{address} …  (keeps the same proxy)"))
        usage.add_row("Terminal", Text(f"export http_proxy=http://{address} https_proxy=http://{address}"))
        usage.add_row("Status (JSON)", Text(f"curl http://{address}/__proxy-scraper/status"))
        usage.add_row("Prometheus", Text(f"http://{address}/__proxy-scraper/metrics"))
        mode = pool.strategy + (f" · sticky {pool.sticky_seconds:g} s" if pool.sticky_seconds else "")
        usage.add_row("Rotation", Text(mode + (f" · {fmt(server.revived)} brought back" if server.revived else ""),
                                       style=MUTED))

        cards = row(
            card("Requests", fmt(st.requests), f"{st.requests / uptime * 60:.1f} per minute"),
            card("Successful", pct(st.ok, st.requests) if st.requests else "–",
                 f"{fmt(st.failed)} failed", f"bold {GOOD}" if not st.failed else f"bold {WARN}"),
            card("Active", fmt(st.active), "open connections", f"bold {ACCENT}"),
            card("Pool", f"{fmt(len(usable))} / {fmt(len(pool.entries))}",
                 f"{fmt(len(pool.tls_capable))} for HTTPS · {fmt(len(pool.entries) - len(usable))} out"),
            card("Traffic", _mb(st.bytes_down), f"↑ {_mb(st.bytes_up)}"),
        )

        recent = table()
        recent.add_column("", width=1)
        recent.add_column("Target", ratio=2, no_wrap=True, overflow="ellipsis")
        recent.add_column("via proxy", ratio=2, no_wrap=True, overflow="ellipsis")
        if width >= 100:
            recent.add_column("Client", style=MUTED, no_wrap=True)
        recent.add_column("Attempts", justify="right", width=8)
        recent.add_column("Time", justify="right", width=8)
        for log in reversed(st.recent):
            ptype = log.via.split("://", 1)[0]
            cells = [
                Text("✔", style=GOOD) if log.ok else Text("✘", style=BAD),
                log.target,
                Text(shown_via(log.via), style=TYPE_STYLE.get(ptype, MUTED)),
            ]
            if width >= 100:
                cells.append(log.client)
            cells += [str(log.attempts), f"{fmt(log.ms)} ms"]
            recent.add_row(*cells)

        busiest = table()
        busiest.add_column("Proxy", no_wrap=True, overflow="ellipsis")
        busiest.add_column("OK", justify="right", style=GOOD)
        busiest.add_column("Errors", justify="right", style=MUTED)
        busiest.add_column("Latency", justify="right")
        for entry in sorted(pool.entries, key=lambda e: (-e.ok, e.result.latency))[:5]:
            r = entry.result
            style = MUTED if entry.disabled else TYPE_STYLE.get(r.ptype, "")
            name = Text(f"{r.ptype}://{shown_proxy(r.proxy)}", style=style)
            busiest.add_row(name, fmt(entry.ok), fmt(entry.fail), f"{fmt(r.latency)} ms")

        waiting = Align.center(Text("waiting for the first connection …", style=MUTED))
        return Group(
            Panel(Group(title, Text(""), usage), box=box.HEAVY, border_style=ACCENT, padding=(0, 1)),
            cards,
            row(
                widgets.panel(recent if st.recent else waiting, "Recent connections", GOOD),
                widgets.panel(busiest, "Most used proxies"),
                ratios=(3, 2),
            ),
            Text("  Ctrl+C stops the server", style=MUTED),
        )


def shown_via(via: str) -> str:
    """'socks5://user:pass@1.2.3.4:1080' -> password masked; '–' (no proxy) stays."""
    scheme, sep, proxy = via.partition("://")
    return f"{scheme}://{shown_proxy(proxy)}" if sep else via
