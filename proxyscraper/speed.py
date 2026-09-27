"""Download speed per proxy – measured for the live list after every run.

The latency of one tiny request says little about loading a real page. So every HTTPS-capable proxy downloads
100 KB from Cloudflare's speed test through a verified TLS tunnel. The rate counts from the request to the last
byte – the tunnel is already open then, so its handshake doesn't drag it down, the first answer does count.
There's a hard deadline: some proxies trickle a few bytes a second and would never finish – their rate is taken
from what arrived by then, which is a real (slow) measurement too.

    python -m proxyscraper.speed results/<run>      # adds "speed_kbps" to proxies.json
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from .runsteps import PROBE_ERRORS, Tunnels, browser_get, https_rows, load_rows, resolve_ipv4, run_limited, save_rows

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
    tunnels = Tunnels(deadline)

    async def probe(row: dict, ip: str) -> Optional[int]:
        end = time.monotonic() + deadline

        async def within(coro):
            return await asyncio.wait_for(coro, max(0.01, end - time.monotonic()))

        try:
            opened = await within(tunnels.open(row, HOST, ip))
            if opened is None:
                return None
            reader, writer = opened
            try:
                # the clock runs from the request to the last byte: a start at the first body byte would miss
                # whatever already sat in the buffer with the head, and fast proxies would come out absurdly fast
                sent = time.monotonic()
                writer.write(browser_get(HOST, PATH, "Accept-Encoding: identity"))
                await within(writer.drain())
                head = await within(reader.readuntil(b"\r\n\r\n"))
                if b" 200 " not in head.split(b"\r\n", 1)[0] + b" ":
                    return None
                received = 0
                while received < BYTES:
                    try:
                        chunk = await within(reader.read(65536))
                    except asyncio.TimeoutError:
                        break  # the deadline: what arrived so far is the measurement
                    if not chunk:
                        break
                    received += len(chunk)
                return kbps(received, time.monotonic() - sent)
            finally:
                writer.close()
        except PROBE_ERRORS:
            return None
    return probe


async def fill_run(run_dir: Path, probe: Optional[Probe] = None, resolve: Callable[[str], str] = resolve_ipv4,
                   concurrency: int = CONCURRENCY) -> Optional[int]:
    """Measure every HTTPS-capable proxy of a run, write speed_kbps into its proxies.json -> the median."""
    probe = probe or real_probe()
    path, rows = load_rows(run_dir)
    try:
        ip = resolve(HOST)
    except OSError:
        return None

    def job(row: dict):
        async def run() -> None:
            try:  # the probe keeps its own deadline – this only catches one that doesn't
                value = await asyncio.wait_for(probe(row, ip), DEADLINE * 1.5)
            except asyncio.TimeoutError:
                value = None
            if value:
                row["speed_kbps"] = value
        return run

    await run_limited((job(r) for r in https_rows(rows)), concurrency)
    save_rows(path, rows)
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
