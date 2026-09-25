"""Python-API: proxy-scraper aus eigenem Code benutzen.

    from proxyscraper import find_proxies

    for p in find_proxies(want=20, https=True, countries=["DE", "NL"]):
        print(p.url, p.latency, p.country)

Dahinter läuft genau dasselbe wie in der Kommandozeile (Quellen, Lernen, Honeypot- und
Manipulationsprüfung, Ergebnisdateien unter results/), nur ohne Ausgabe im Terminal.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import tempfile
from typing import Iterable, List, Optional

from rich.console import Console

from .checker import CheckResult
from .options import Filters, RunOptions, parse_countries
from .parsing import PROXY_TYPES
from .ui import widgets

__all__ = ["CheckResult", "check_proxies", "check_proxies_async", "find_proxies", "find_proxies_async"]


def _options(types: Iterable[str], want: int, limit: int, https: bool, countries: Iterable[str], anonymity: str,
             max_latency: int, targets: Iterable[str], no_datacenter: bool, timeout: float, concurrency: int,
             recheck: Optional[str]) -> RunOptions:
    if isinstance(countries, str):
        countries = parse_countries(countries)
    return RunOptions(
        types=list(types),
        filters=Filters(countries={c.upper() for c in countries}, https_only=https, min_anonymity=anonymity,
                        max_latency=max_latency, targets=list(targets), no_datacenter=no_datacenter),
        want=want, limit=limit, timeout=timeout, concurrency=concurrency, recheck=recheck,
    )


@contextlib.contextmanager
def _quiet(verbose: bool):
    """Die Oberfläche schreibt auf widgets.console – für die API in einen Puffer statt ins Terminal."""
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
    """Proxys sammeln und prüfen; gibt die Treffer zurück, die alle Filter erfüllen, schnellste zuerst.

    want        aufhören, sobald so viele passende Proxys gefunden sind (0 = alles prüfen)
    limit       nur die N vielversprechendsten Kandidaten prüfen (0 = alle)
    https       nur Proxys, die HTTPS mit verifiziertem TLS tunneln
    countries   z. B. ["DE", "AT"] oder "DE,AT"
    anonymity   "anonymous" oder "elite" als Mindeststufe
    max_latency in Millisekunden (0 = egal)
    targets     Seiten, die jeder Proxy erreichen muss, z. B. ["google.com"]
    verbose     die normale Oberfläche im Terminal zeigen
    """
    from .app import Run  # erst hier: app zieht die ganze Oberfläche nach

    opts = _options(types, want, limit, https, countries, anonymity, max_latency, targets, no_datacenter,
                    timeout, concurrency, _recheck)
    with _quiet(verbose):
        run = Run(opts, show_banner=verbose)
        await run.execute()
    return sorted(run.kept, key=lambda r: r.latency)


def find_proxies(**kwargs) -> List[CheckResult]:
    """Wie find_proxies_async, nur synchron (startet eine eigene Event-Loop)."""
    return asyncio.run(find_proxies_async(**kwargs))


async def check_proxies_async(proxies: Iterable[str], **kwargs) -> List[CheckResult]:
    """Eigene Proxys prüfen ("socks5://1.2.3.4:1080", "http://user:pass@…", "1.2.3.4:8080" = HTTP).
    Nimmt dieselben Filter wie find_proxies; gesammelt wird nichts."""
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
