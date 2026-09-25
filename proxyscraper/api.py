"""Python API: use proxy-scraper from your own code.

    from proxyscraper import find_proxies

    if __name__ == "__main__":  # important on macOS/Windows, see below
        for p in find_proxies(want=20, https=True, countries=["DE", "NL"]):
            print(p.url, p.latency, p.country)

Behind it runs exactly the same as on the command line (sources, learning, honeypot and
tampering checks, result files under results/), just without output in the terminal.

Large lists are parsed in a process pool. On macOS and Windows it starts the worker processes
with "spawn", which re-imports the calling script – as with any code that uses multiprocessing,
the call therefore belongs behind `if __name__ == "__main__":`.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import tempfile
import threading
from typing import Iterable, List, Optional

from rich.console import Console

from .checker import CheckResult
from .options import Filters, RunOptions, parse_countries
from .parsing import PROXY_TYPES
from .targets import parse_target
from .ui import widgets

__all__ = ["CheckResult", "check_proxies", "check_proxies_async", "find_proxies", "find_proxies_async"]


def _options(types: Iterable[str], want: int, limit: int, https: bool, countries: Iterable[str], anonymity: str,
             max_latency: int, targets: Iterable[str], no_datacenter: bool, timeout: float, concurrency: int,
             recheck: Optional[str]) -> RunOptions:
    if isinstance(countries, str):
        countries = parse_countries(countries)
    if anonymity not in ("", "anonymous", "elite"):
        raise ValueError(f"anonymity must be '', 'anonymous' or 'elite', not {anonymity!r}")
    # like the CLI: "google.com" -> "https://google.com/", duplicates dropped, invalid targets -> ValueError
    targets = list(dict.fromkeys(parse_target(t).url for t in targets))
    return RunOptions(
        types=list(types),
        filters=Filters(countries={c.upper() for c in countries}, https_only=https, min_anonymity=anonymity,
                        max_latency=max_latency, targets=targets, no_datacenter=no_datacenter),
        want=want, limit=limit, timeout=timeout, concurrency=concurrency, recheck=recheck,
    )


# one run after the other: console, history and source statistics are global, and a run uses thousands
# of connections at once anyway. A threading.Lock, so this also holds across threads and event loops.
_RUN_LOCK = threading.Lock()


@contextlib.asynccontextmanager
async def _one_at_a_time():
    # wait without blocking: the event loop keeps running, and cancelling while waiting leaves no lock behind
    while not _RUN_LOCK.acquire(blocking=False):
        await asyncio.sleep(0.05)
    try:
        yield
    finally:
        _RUN_LOCK.release()


@contextlib.contextmanager
def _quiet(verbose: bool):
    """The UI writes to widgets.console – for the API into a buffer instead of the terminal."""
    if verbose:
        yield
        return
    original = widgets.console
    widgets.console = Console(file=io.StringIO(), width=120)
    try:
        yield
    finally:
        widgets.console = original


async def find_proxies_async(*, types: Iterable[str] = PROXY_TYPES, want: int = 0, limit: int = 0,
                             https: bool = False, countries: Iterable[str] = (), anonymity: str = "",
                             max_latency: int = 0, targets: Iterable[str] = (), no_datacenter: bool = False,
                             timeout: float = 8.0, concurrency: int = 2000, verbose: bool = False,
                             _recheck: Optional[str] = None) -> List[CheckResult]:
    """Collect and check proxies; returns the hits that pass every filter, fastest first.

    want        stop as soon as this many matching proxies are found (0 = check everything)
    limit       only check the N most promising candidates (0 = all)
    https       only proxies that tunnel HTTPS with verified TLS
    countries   e.g. ["DE", "AT"] or "DE,AT"
    anonymity   "anonymous" or "elite" as the minimum level
    max_latency in milliseconds (0 = any)
    targets     sites every proxy has to reach, e.g. ["google.com"]
    verbose     show the normal terminal UI
    """
    from .app import Run  # only here: app pulls in the whole UI

    opts = _options(types, want, limit, https, countries, anonymity, max_latency, targets, no_datacenter,
                    timeout, concurrency, _recheck)
    async with _one_at_a_time():
        with _quiet(verbose):
            run = Run(opts, show_banner=verbose)
            await run.execute()
    found = sorted(run.kept, key=lambda r: r.latency)
    # when stopping after `want`, the checks still in flight finish – the CLI writes all of them to the
    # files, the API returns exactly as many as requested (the fastest)
    return found[:want] if want else found


def find_proxies(**kwargs) -> List[CheckResult]:
    """Like find_proxies_async, just synchronous (starts its own event loop)."""
    return asyncio.run(find_proxies_async(**kwargs))


async def check_proxies_async(proxies: Iterable[str], **kwargs) -> List[CheckResult]:
    """Check your own proxies ("socks5://1.2.3.4:1080", "http://user:pass@…", "1.2.3.4:8080" = HTTP).
    Takes the same filters as find_proxies; nothing is collected."""
    lines = [p.strip() for p in proxies if p and p.strip()]
    lines = [p if "://" in p else f"http://{p}" for p in lines]
    fd, path = tempfile.mkstemp(prefix="proxy-scraper-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return await find_proxies_async(_recheck=path, **kwargs)
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


def check_proxies(proxies: Iterable[str], **kwargs) -> List[CheckResult]:
    return asyncio.run(check_proxies_async(proxies, **kwargs))
