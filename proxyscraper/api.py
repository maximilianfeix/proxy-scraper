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
import email.message
import io
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from rich.console import Console

from .checker import CheckResult
from .options import Filters, RunOptions, parse_countries
from .parsing import PROXY_TYPES
from .targets import parse_target
from .ui import widgets

__all__ = [
    "CheckResult",
    "LiveProxy",
    "ProxyResponse",
    "ProxyRotator",
    "check_proxies",
    "check_proxies_async",
    "find_proxies",
    "find_proxies_async",
    "live_proxies",
    "live_proxies_async",
]


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
    sites: Dict[str, bool] = field(default_factory=dict)  # "google", "reddit", … -> got through in the last run?
    speed_kbps: Optional[int] = None  # download speed in KiB/s in the last run (HTTPS-capable ones only)


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
        sites={k: v for k, v in (row.get("sites") or {}).items() if isinstance(v, bool)},
        speed_kbps=row.get("speed_kbps") if type(row.get("speed_kbps")) is int else None)


async def live_proxies_async(*, types: Iterable[str] = PROXY_TYPES, countries: Iterable[str] = (), https: bool = False,
                             anonymity: str = "", max_latency: int = 0, no_datacenter: bool = False,
                             no_blocklisted: bool = False, min_uptime: int = 0, works_on: Iterable[str] = (),
                             min_speed: int = 0, limit: int = 0) -> List[LiveProxy]:
    """The proxies from the hourly list that pass the filters, fastest first – by first answer plus measured
    download speed. Nothing is checked here: they worked from GitHub's servers in the last run (at most an hour
    ago). find_proxies checks from your network.

    Same filters as find_proxies, plus
    min_uptime  only proxies listed in at least this share (percent) of the week's runs, e.g. 90
    works_on    only proxies that got through to these sites in the last run: google, reddit, amazon, instagram,
                tiktok
    min_speed   only proxies that downloaded at least this many KiB/s in the last run
    limit       at most this many (0 = all)
    """
    from .agent import AgentError, LiveSource
    from .server.pool import page_ms
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
    works_on = [str(s).lower() for s in ([works_on] if isinstance(works_on, str) else works_on)]
    unknown_sites = [s for s in works_on if s not in SITE]
    if unknown_sites:
        raise ValueError(f"works_on takes {', '.join(SITE)}, not {unknown_sites[0]!r}")
    opts = _options(types, 0, 0, https, countries, anonymity, max_latency, (), no_datacenter, no_blocklisted, 8.0, 1,
                    None)
    try:
        data = await LiveSource(fetch=_live_fetch).get()
    except AgentError as e:
        raise ConnectionError(str(e)) from None
    found = [_live_proxy(r, data.run_hours) for r in data.rows
             if r.get("ptype") in types and isinstance(r.get("proxy"), str)]
    # fastest first – by how quickly a page comes through when the list has download speeds (#186)
    known = any(p.speed_kbps for p in found)
    found.sort(key=lambda p: page_ms(p, known))
    found = [p for p in found if opts.filters.accepts(p) and (not min_uptime or (p.uptime_7d or 0) >= min_uptime)
             and all(p.sites.get(s) for s in works_on) and (not min_speed or (p.speed_kbps or 0) >= min_speed)]
    return found[:limit] if limit else found


def live_proxies(**kwargs) -> List[LiveProxy]:
    """Like live_proxies_async, just synchronous (starts its own event loop)."""
    return asyncio.run(live_proxies_async(**kwargs))


# --------------------------------------------------------------------------- fetching through the list

class _Headers(dict):
    """Response headers: looked up without regard to case, the first value per name as a plain dict entry,
    and every value – Set-Cookie comes more than once – through get_all()."""

    def __init__(self, items: Iterable[Tuple[str, str]] = ()):
        self._items = list(items)
        super().__init__()
        for name, value in self._items:
            super().setdefault(name.lower(), value)

    def __getitem__(self, name: str) -> str:
        return super().__getitem__(name.lower())

    def get(self, name: str, default=None):
        return super().get(name.lower(), default)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and super().__contains__(name.lower())

    def get_all(self, name: str) -> List[str]:
        return [value for key, value in self._items if key.lower() == name.lower()]


@dataclass
class ProxyResponse:
    """What ProxyRotator.get() returns."""
    status: int
    url: str
    final_url: str                     # after redirects
    headers: _Headers                  # case doesn't matter; headers.get_all("Set-Cookie") for repeated ones
    content: bytes
    via: Optional[str]                 # the proxy that delivered it, e.g. socks5://1.2.3.4:1080
    proxy_country: Optional[str]
    elapsed_ms: int
    truncated: bool = False            # the body was longer than 2 MB and is cut off

    @property
    def text(self) -> str:
        message = email.message.Message()
        message["Content-Type"] = self.headers.get("Content-Type", "")
        charset = message.get_content_charset() or "utf-8"  # handles charset="…" and any case, like a browser
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:  # a charset Python doesn't know
            return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise ConnectionError(f"HTTP {self.status} from {self.final_url} (via {self.via})")
        if self.truncated:
            raise ConnectionError(f"the body from {self.final_url} was cut off at 2 MB")


class ProxyRotator:
    """Loads URLs through proxies from the hourly list and switches to the next one when a proxy fails –
    the loop every scraper writes by hand. HTTPS only through proxies with verified TLS.

        with ProxyRotator(country="DE") as rotator:
            print(rotator.get("https://api.ipify.org").text)

    Behind it runs the same rotating server as `proxy-scraper --serve`, on 127.0.0.1 with a random password.
    Use it either sync (`get()`, safe from several threads) or async (`aget()` with `async with`) – not both on
    the same rotator. Private and local addresses are refused. Bodies are cut at 2 MB (`truncated`).
    """

    def __init__(self, *, protocol: str = "any", country: str = "", timeout: float = 20.0,
                 _source=None, _allow_private: bool = False):
        self.protocol, self.country, self.timeout = protocol, country, timeout
        self._source, self._allow_private = _source, _allow_private
        self._fetcher = None
        self._mode: Optional[str] = None  # "sync" or "async" – their proxy servers live on different loops
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # the sync API's own loop, in a thread
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()

    def _use(self, mode: str) -> None:
        if self._mode is None:
            self._mode = mode
        elif self._mode != mode:
            raise RuntimeError(f"this ProxyRotator is used {self._mode}hronously – make a second one for "
                               f"{mode} code (sync: get()/close(), async: aget()/async with)")

    def _make_fetcher(self):
        from .agent import LiveSource, PageFetcher

        return PageFetcher(self._source or LiveSource(fetch=_live_fetch), allow_private=self._allow_private,
                           timeout=self.timeout)

    async def aget(self, url: str) -> ProxyResponse:
        self._use("async")
        return await self._aget(url)

    async def _aget(self, url: str) -> ProxyResponse:
        from .agent import AgentError

        if self._fetcher is None:
            self._fetcher = self._make_fetcher()
        try:
            url = await asyncio.to_thread(self._fetcher.check, url)
        except AgentError as e:
            raise ValueError(str(e)) from None
        try:
            page = await self._fetcher.fetch(url, self.protocol, self.country, max_chars=0, raw_html=True,
                                             with_body=True)
        except AgentError as e:
            raise ConnectionError(str(e)) from None
        return ProxyResponse(status=page["status"], url=url, final_url=page["final_url"],
                             headers=_Headers(page["header_items"]), content=page["body"], via=page["via"],
                             proxy_country=page["proxy_country"], elapsed_ms=page["elapsed_ms"],
                             truncated=page["body_truncated"])

    async def aclose(self) -> None:
        if self._fetcher is not None:
            await self._fetcher.close()
            self._fetcher = None

    async def __aenter__(self) -> "ProxyRotator":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    # sync: one event loop in a background thread keeps the proxy server alive between calls
    def get(self, url: str) -> ProxyResponse:
        with self._start_lock:  # several threads calling get() at once still share one loop
            self._use("sync")
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, name="proxy-rotator", daemon=True)
                self._thread.start()
        return asyncio.run_coroutine_threadsafe(self._aget(url), self._loop).result()

    def close(self) -> None:
        with self._start_lock:
            if self._loop is None:
                return
            asyncio.run_coroutine_threadsafe(self.aclose(), self._loop).result()
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            self._loop.close()
            self._thread = None

    def __enter__(self) -> "ProxyRotator":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
