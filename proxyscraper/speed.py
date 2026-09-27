"""Download speed per proxy – measured for the live list after every run.

The latency of one tiny request says little about loading a real page. So every HTTPS-capable proxy downloads
100 KB from Cloudflare's speed test through a verified TLS tunnel. The rate counts from the first byte of the
body, so the handshake doesn't drag it down. There's a hard deadline: some proxies trickle a few bytes a second
and would never finish – their rate is taken from what arrived by then, which is a real (slow) measurement too.

    python -m proxyscraper.speed results/<run>      # adds "speed_kbps" to proxies.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import statistics
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from .netio import USER_AGENT
from .paths import atomic_write

HOST = "speed.cloudflare.com"
BYTES = 100_000
PATH = f"/__down?bytes={BYTES}"
DEADLINE = 12.0         # seconds per proxy, from connect to the last byte
MIN_BYTES = 20_000      # less than this says nothing about the speed
CONCURRENCY = 150

Probe = Callable[[dict, str], Awaitable[Optional[int]]]


def kbps(received: int, seconds: float) -> Optional[int]:
    """KiB per second, or None when too little arrived to tell."""
    if received < MIN_BYTES or seconds <= 0:
        return None
    return max(1, round(received / 1024 / seconds))


def real_probe(deadline: float = DEADLINE) -> Probe:
    from .checker import Checker

    checker = Checker(judge_ip="127.0.0.1", own_ips=(), timeout=deadline, connect_timeout=deadline / 2)

    async def probe(row: dict, ip: str) -> Optional[int]:
        end = time.monotonic() + deadline

        async def within(coro):
            return await asyncio.wait_for(coro, max(0.01, end - time.monotonic()))

        try:
            opened = await within(checker._tls_tunnel(row["ptype"], row["proxy"], HOST, socket.inet_aton(ip), 443))
            if opened is None:
                return None
            reader, writer = opened
            try:
                writer.write(f"GET {PATH} HTTP/1.1\r\nHost: {HOST}\r\nUser-Agent: {USER_AGENT}\r\n"
                             "Accept-Encoding: identity\r\nConnection: close\r\n\r\n".encode())
                await within(writer.drain())
                head = await within(reader.readuntil(b"\r\n\r\n"))
                if b" 200 " not in head.split(b"\r\n", 1)[0] + b" ":
                    return None
                received, started = 0, None
                while received < BYTES:
                    try:
                        chunk = await within(reader.read(65536))
                    except asyncio.TimeoutError:
                        break  # the deadline: what arrived so far is the measurement
                    if not chunk:
                        break
                    if started is None:
                        started = time.monotonic()
                    received += len(chunk)
                if started is None:
                    return None
                return kbps(received, time.monotonic() - started)
            finally:
                writer.close()
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError):
            return None
    return probe


def _resolve(host: str) -> str:
    return socket.getaddrinfo(host, 443, family=socket.AF_INET)[0][4][0]


async def fill_run(run_dir: Path, probe: Optional[Probe] = None, resolve: Callable[[str], str] = _resolve,
                   concurrency: int = CONCURRENCY) -> Optional[int]:
    """Measure every HTTPS-capable proxy of a run, write speed_kbps into its proxies.json -> the median."""
    probe = probe or real_probe()
    path = run_dir / "proxies.json"
    rows: List[dict] = json.loads(path.read_text(encoding="utf-8"))
    try:
        ip = resolve(HOST)
    except OSError:
        return None
    slots = asyncio.Semaphore(concurrency)

    async def one(row: dict) -> None:
        async with slots:
            try:  # the probe keeps its own deadline – this only catches one that doesn't
                value = await asyncio.wait_for(probe(row, ip), DEADLINE * 1.5)
            except asyncio.TimeoutError:
                value = None
        if value:
            row["speed_kbps"] = value

    await asyncio.gather(*(one(r) for r in rows if r.get("https") is True))
    atomic_write(path, json.dumps(rows, indent=1, ensure_ascii=False))
    speeds = [r["speed_kbps"] for r in rows if r.get("speed_kbps")]
    return round(statistics.median(speeds)) if speeds else None


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="measure the download speed of the proxies of a run")
    p.add_argument("run_dir", type=Path)
    args = p.parse_args(argv)
    started = time.monotonic()
    median = asyncio.run(fill_run(args.run_dir))
    print(f"median download speed: {median} KiB/s ({time.monotonic() - started:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
