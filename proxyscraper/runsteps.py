"""Shared plumbing for the extra steps that run on a finished run's proxies.json in the hourly workflow –
which sites let a proxy through (sites.py), how fast it downloads (speed.py).

Each step loads the run's rows, tries the HTTPS-capable proxies through a verified TLS tunnel with a limit on how
many at once, and writes the file back in one go: if the workflow kills the step at its timeout, the publish step
still finds the old file intact.
"""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from typing import Awaitable, Callable, Iterable, List, Tuple

from .paths import atomic_write

# what a probe through a free proxy can run into – all of it just means "no answer from this one"
PROBE_ERRORS = (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError)


def load_rows(run_dir: Path) -> Tuple[Path, List[dict]]:
    path = run_dir / "proxies.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def save_rows(path: Path, rows: List[dict]) -> None:
    atomic_write(path, json.dumps(rows, indent=1, ensure_ascii=False))


def https_rows(rows: Iterable[dict]) -> List[dict]:
    """Only these can tunnel to an https:// site – the others failed the HTTPS test in the run."""
    return [r for r in rows if r.get("https") is True]


def resolve_ipv4(host: str, port: int = 443) -> str:
    """Looked up once per step: SOCKS4 needs the IP, and a thousand lookups of the same host help nobody."""
    return socket.getaddrinfo(host, port, family=socket.AF_INET)[0][4][0]


async def run_limited(jobs: Iterable[Callable[[], Awaitable[None]]], concurrency: int) -> None:
    """Run the jobs with at most `concurrency` at a time."""
    slots = asyncio.Semaphore(concurrency)

    async def one(job: Callable[[], Awaitable[None]]) -> None:
        async with slots:
            await job()

    await asyncio.gather(*(one(job) for job in jobs))


class Tunnels:
    """Verified TLS tunnels to a host through a proxy – the same handshake code the checks use."""

    def __init__(self, timeout: float):
        from .checker import Checker  # only here: the checker pulls in more than these steps need

        self.checker = Checker(judge_ip="127.0.0.1", own_ips=(), timeout=timeout, connect_timeout=timeout / 2)

    async def open(self, row: dict, host: str, ip: str, port: int = 443):
        """(reader, writer) of the TLS connection, or None if the proxy refused the tunnel or broke up the TLS."""
        return await self.checker.tls_tunnel(row["ptype"], row["proxy"], host, ip, port)


def browser_get(host: str, path: str, *extra: str) -> bytes:
    """A plain GET the way a browser would send it (so sites answer as they would to a person)."""
    from .netio import USER_AGENT, host_header

    lines = [f"GET {path} HTTP/1.1", f"Host: {host_header(host, None, True)}", f"User-Agent: {USER_AGENT}",
             "Accept: text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language: en-US,en;q=0.8", *extra,
             "Connection: close"]
    return ("\r\n".join(lines) + "\r\n\r\n").encode()

