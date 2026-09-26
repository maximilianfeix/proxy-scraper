"""Python API: use proxy-scraper from your own code.

    from proxyscraper import find_proxies

    if __name__ == "__main__":  # important on macOS/Windows, see below
        for p in find_proxies(want=20, https=True, countries=["DE", "NL"]):
            print(p.url, p.latency, p.country)

Or skip the checking and take the list that GitHub Actions checks every hour:

    from proxyscraper import live_proxies

    for p in live_proxies(types=["socks5"], countries="DE", https=True, min_uptime=90):
        print(p.url, p.latency, p.uptime_7d)

Behind find_proxies runs exactly the same as on the command line (sources, learning, honeypot and
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
import re
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from rich.console import Console

from .checker import CheckResult
from .options import Filters, RunOptions, parse_countries
from .parsing import PROXY_TYPES
from .targets import parse_target
from .ui import widgets

__all__ = ["CheckResult", "LiveProxy", "check_proxies", "check_proxies_async", "find_proxies", "find_proxies_async",
           "live_proxies", "live_proxies_async"]


def _types(types: Iterable[str]) -> List[str]:
    """["socks5"], "socks5" or "socks5,http" – a plain string shouldn't turn into its letters."""
    if isinstance(types, str):
        return [t.strip().lower() for t in types.split(",") if t.strip()]
    return list(types)


def _options(types: Iterable[str], want: int, limit: int, https: bool, countries: Iterable[str], anonymity: str,
             max_latency: int, targets: Iterable[str], no_datacenter: bool, no_blocklisted: bool, timeout: float,
             concurrency: int,
             recheck: Optional[str]) -> RunOptions:
    types = _types(types)
    if isinstance(countries, str):
        countries = parse_countries(countries)
    if anonymity not in ("", "anonymous", "elite"):
        raise ValueError(f"anonymity must be '', 'anonymous' or 'elite', not {anonymity!r}")
    # like the CLI: "google.com" -> "https://google.com/", duplicates dropped, invalid targets -> ValueError
    targets = list(dict.fromkeys(parse_target(t).url for t in targets))
    return RunOptions(
        types=list(types),
        filters=Filters(countries={c.upper() for c in countries}, https_only=https, min_anonymity=anonymity,
                        max_latency=max_latency, targets=targets, no_datacenter=no_datacenter,
                        no_blocklisted=no_blocklisted),
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
                             no_blocklisted: bool = False,
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
                    no_blocklisted, timeout, concurrency, _recheck)
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


# --------------------------------------------------------------------------- the hourly list

@dataclass
class LiveProxy(CheckResult):
    """A proxy from the hourly list: the same fields as a CheckResult, plus how reliable it has been."""
    uptime_24h: Optional[int] = None  # share of today's hourly runs it was listed in, in percent
    uptime_7d: Optional[int] = None   # the same over the week
    first_seen: str = ""              # ISO time of the first run it was listed in
    up_for_hours: int = 0             # listed without a gap for this long
    sites: Dict[str, bool] = field(default_factory=dict)  # "google", "reddit", "amazon" -> got through last run?


def _live_fetch(url: str, timeout: float = 20, headers=None):
    from .netio import http_get
    return http_get(url, timeout=timeout, headers=headers)


def _live_proxy(row: dict, run_hours: int) -> LiveProxy:
    streak = row.get("streak") if type(row.get("streak")) is int else 0
    return LiveProxy(
        key=f"{row['ptype']} {row['proxy']}", ptype=row["ptype"], proxy=row["proxy"],
        latency=int(row.get("latency") or 0),
        exit_ip=row.get("exit_ip") or "", https=row.get("https"), anonymity=row.get("anonymity") or "",
        country=row.get("country") or "", targets=dict(row.get("targets") or {}), asn=row.get("asn") or 0,
        org=row.get("org") or "", hosting=row.get("hosting"), blocklisted=row.get("blocklisted"),
        uptime_24h=row.get("uptime_24h"), uptime_7d=row.get("uptime_7d"), first_seen=row.get("first_seen") or "",
        up_for_hours=streak * run_hours,
        sites={k: v for k, v in (row.get("sites") or {}).items() if isinstance(v, bool)})


async def live_proxies_async(*, types: Iterable[str] = PROXY_TYPES, countries: Iterable[str] = (), https: bool = False,
                             anonymity: str = "", max_latency: int = 0, no_datacenter: bool = False,
                             no_blocklisted: bool = False, min_uptime: int = 0, works_on: Iterable[str] = (),
                             limit: int = 0) -> List[LiveProxy]:
    """The proxies from the hourly list that pass the filters, fastest first. Nothing is checked here: they
    worked from GitHub's servers in the last run (at most an hour ago). find_proxies checks from your network.

    Same filters as find_proxies, plus
    min_uptime  only proxies listed in at least this share (percent) of the week's runs, e.g. 90
    works_on    only proxies that got through to these sites in the last run: "google", "reddit", "amazon"
    limit       at most this many (0 = all)
    """
    from .agent import AgentError, LiveSource
    from .sites import SITE

    types = _types(types)
    unknown = [t for t in types if t not in PROXY_TYPES]
    if unknown:
        raise ValueError(f"unknown proxy type {unknown[0]!r}, use {', '.join(PROXY_TYPES)}")
    if isinstance(countries, str):
        countries = parse_countries(countries)
    countries = {c.strip().upper() for c in countries}
    bad = [c for c in countries if not re.fullmatch(r"[A-Z]{2}", c)]
    if bad:
        raise ValueError(f"countries are two-letter codes like DE or US, not {bad[0]!r}")
    works_on = [works_on] if isinstance(works_on, str) else [str(s).lower() for s in works_on]
    unknown_sites = [s for s in works_on if s not in SITE]
    if unknown_sites:
        raise ValueError(f"works_on takes {', '.join(SITE)}, not {unknown_sites[0]!r}")
    opts = _options(types, 0, 0, https, countries, anonymity, max_latency, (), no_datacenter, no_blocklisted, 8.0, 1,
                    None)
    try:
        data = await LiveSource(fetch=_live_fetch).get()
    except AgentError as e:
        raise ConnectionError(str(e)) from None
    found = sorted((_live_proxy(r, data.run_hours) for r in data.rows
                    if r.get("ptype") in types and isinstance(r.get("proxy"), str)),
                   key=lambda p: p.latency)
    found = [p for p in found if opts.filters.accepts(p) and (not min_uptime or (p.uptime_7d or 0) >= min_uptime)
             and all(p.sites.get(s) for s in works_on)]
    return found[:limit] if limit else found


def live_proxies(**kwargs) -> List[LiveProxy]:
    """Like live_proxies_async, just synchronous (starts its own event loop)."""
    return asyncio.run(live_proxies_async(**kwargs))
