"""Ablauf: Quellen zusammenstellen, parallel laden & parsen, priorisieren, prüfen."""

from __future__ import annotations

import asyncio
import contextlib
import os
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from . import sources as srcs
from .checker import Checker, CheckResult
from .compat import on_interrupt
from .fetchcache import FetchCache
from .geo import GeoResolver
from .history import ProxyHistory
from .judges import JudgeWatch
from .netio import http_get, http_request
from .options import RunOptions
from .output import ResultWriter
from .parsing import PROXY_TYPES, parse_blob, split_key
from .ui import ACCENT, CheckDashboard, CollectView, fmt, widgets

AUTO_DISCOVER_AFTER_DAYS = 3.0
# Kleine Listen direkt parsen – der Umweg über einen anderen Prozess kostet mehr, als er spart
INLINE_PARSE_BYTES = 256 * 1024
DOWNLOAD_CONCURRENCY = 64


# --------------------------------------------------------------------------- #
# Quellen
# --------------------------------------------------------------------------- #

@dataclass
class SourcePlan:
    sources: Dict[str, str]
    skipped: Counter
    n_curated: int
    n_meta: int
    meta_ok: int
    meta_total: int
    n_discovered: int
    discovery_ran: bool = False
    discovery_token: bool = False


async def collect_sources(opts: RunOptions, quality: srcs.SourceStats) -> SourcePlan:
    """Kuratierte + Meta- + entdeckte Quellen, abzüglich der gelernt schlechten."""
    sources, meta = srcs.load_source_file()
    n_curated = len(sources)

    age = srcs.discovered_age_days()
    token = srcs.github_token() if (opts.discover or not opts.no_discover) else None
    run_discovery = opts.discover or (
        not opts.no_discover and token is not None and (age is None or age > AUTO_DISCOVER_AFTER_DAYS)
    )
    if run_discovery:
        max_repos = opts.discover_repos if token else min(opts.discover_repos, 40)
        with widgets.console.status(f"[bold {ACCENT}]Suche neue Proxy-Listen auf GitHub …", spinner="dots") as status:
            found = await srcs.discover_github(
                http_get, token, max_repos,
                on_progress=lambda msg: status.update(f"[bold {ACCENT}]GitHub-Discovery:[/] {msg}"),
            )
        if found:
            srcs.save_discovered(found)
    discovered = srcs.load_discovered()

    with widgets.console.status(f"[bold {ACCENT}]Lade Meta-Quellen …", spinner="dots"):
        meta_found, meta_ok = await srcs.resolve_meta(meta, http_get)
    for extra in (meta_found, discovered):
        for url, ptype in extra.items():
            sources.setdefault(url, ptype)

    wanted = set(opts.types)
    sources = {u: t for u, t in sources.items() if t == "auto" or t in wanted}
    skipped: Counter = Counter()
    if not opts.all_sources:
        active = {}
        for url, ptype in sources.items():
            reason = quality.skip_reason(url)
            if reason:
                skipped[reason] += 1
            else:
                active[url] = ptype
        sources = active
    return SourcePlan(
        sources, skipped, n_curated, len(meta_found), meta_ok, len(meta), len(discovered),
        discovery_ran=run_discovery, discovery_token=token is not None,
    )


@dataclass
class ScrapeResult:
    urls: List[str]
    # Proxy-Schlüssel -> Indizes der Quellen, die ihn listen (für Priorität und Statistik)
    index: Dict[str, List[int]] = field(default_factory=dict)
    ok_sources: int = 0


async def scrape(sources: Dict[str, str], types, quality: srcs.SourceStats, view: CollectView,
                 cache: Optional[FetchCache] = None) -> ScrapeResult:
    """Lädt alle Quellen und parst große Listen parallel auf allen CPU-Kernen.

    Die Event-Loop bleibt dadurch frei für weitere Downloads, statt minutenlang Regexe abzuarbeiten.
    Mit Cache werden unveränderte Listen per ETag übersprungen (siehe fetchcache.py).
    """
    res = ScrapeResult(list(sources))
    cache = cache or FetchCache(enabled=False)
    # Für den Cache immer alle Typen parsen, gefiltert wird erst beim Einsortieren
    parse_types = PROXY_TYPES if cache.enabled else tuple(types)
    prefixes = tuple(f"{t} " for t in types)
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    index = res.index

    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:

        async def download(url: str):
            """-> (Daten, Schlüssel aus dem Cache). Genau eins von beiden ist gesetzt."""
            conditional = cache.conditional_headers(url, sources[url])
            async with sem:
                status, headers, body = await http_request(url, timeout=30, headers=conditional or None)
            if status == 304 and conditional:
                cached = cache.load(url)
                if cached is not None:
                    return None, headers, cached
                async with sem:  # Cache-Datei kaputt -> normal neu laden
                    status, headers, body = await http_request(url, timeout=30)
            if status != 200:
                raise ConnectionError(f"HTTP {status}")
            return body, headers, None

        async def fetch(i: int, url: str) -> None:
            data: Optional[bytes] = None
            keys = ""
            unchanged = False
            try:
                data, headers, cached = await download(url)
                if cached is not None:
                    keys, unchanged = cached, True
                    view.cached += 1
                else:
                    view.bytes += len(data)
                    if len(data) <= INLINE_PARSE_BYTES:
                        keys = parse_blob(data, sources[url], parse_types)
                    else:
                        keys = await loop.run_in_executor(pool, parse_blob, data, sources[url], parse_types)
                    cache.store(url, headers, keys, sources[url])
            except Exception:  # Quelle nicht erreichbar/kaputt – zählt in der Statistik als Fehlschlag
                pass
            n = 0
            if keys:
                for key in keys.split("\n"):
                    if not key.startswith(prefixes):
                        continue
                    owners = index.get(key)
                    if owners is None:
                        index[key] = [i]
                    else:
                        owners.append(i)
                    n += 1
            quality.record_fetch(url, data, n, unchanged=unchanged)
            if n:
                res.ok_sources += 1
                view.ok += 1
            else:
                view.failed += 1
            view.unique = len(index)
            view.advance()

        await asyncio.gather(*(fetch(i, u) for i, u in enumerate(res.urls)))
    return res


def prioritize(res: ScrapeResult, quality: srcs.SourceStats, history: ProxyHistory, types) -> List[str]:
    """Reihenfolge der Prüfung: bekannte funktionierende Proxys zuerst, dann nach Qualität der Quellen.

    Innerhalb gleicher Quellenqualität gewinnen Proxys, die in mehr Listen stehen.
    """
    wanted = set(types)
    known = [k for k in history.ranked_keys() if split_key(k)[0] in wanted]
    known_set = set(known)

    scores = [quality.score(u) for u in res.urls]
    keys = [k for k in res.index if k not in known_set]
    random.shuffle(keys)  # echten Gleichstand zufällig mischen, damit alle Typen vorankommen
    index = res.index

    def priority(key: str) -> float:
        owners = index[key]
        if len(owners) == 1:
            return scores[owners[0]]
        return max(map(scores.__getitem__, owners)) + 0.002 * min(len(owners), 10)

    prio = list(map(priority, keys))
    order = sorted(range(len(keys)), key=prio.__getitem__, reverse=True)
    return known + [keys[i] for i in order]


def attribute_results(res: ScrapeResult, checked: List[str], working: Set[str]) -> Dict[str, Tuple[int, int]]:
    """Ergebnisse den Quellen zuordnen -> url -> (geprüft, funktionierend)."""
    n_checked = [0] * len(res.urls)
    n_working = [0] * len(res.urls)
    for key in checked:
        ok = key in working
        for i in res.index.get(key, ()):
            n_checked[i] += 1
            if ok:
                n_working[i] += 1
    return {u: (n_checked[i], n_working[i]) for i, u in enumerate(res.urls) if n_checked[i]}


def best_sources(per_source: Dict[str, Tuple[int, int]], limit: int = 10, min_checked: int = 30):
    return sorted(
        ((w / c, w, c, u) for u, (c, w) in per_source.items() if c >= min_checked and w),
        reverse=True,
    )[:limit]


# --------------------------------------------------------------------------- #
# Prüfen
# --------------------------------------------------------------------------- #

@dataclass
class CheckRun:
    results: List[CheckResult] = field(default_factory=list)
    checked: List[str] = field(default_factory=list)
    working: Set[str] = field(default_factory=set)
    interrupted: bool = False
    reached_goal: bool = False
    judge_switches: List[str] = field(default_factory=list)  # "alt → neu"
    rechecked: int = 0  # Prüfungen, die wegen eines ausgefallenen Prüfziels wiederholt wurden


class JobQueue:
    """Iterator über die Jobs, der auch nach dem Leerlaufen noch Nachzügler annimmt.

    Ein Generator wäre nach dem ersten StopIteration für immer erschöpft – dann würde ein Proxy,
    den ein noch laufender Worker nach einem Prüfziel-Wechsel zurücklegt, nie mehr geprüft."""

    def __init__(self, jobs: Iterable[str]):
        self.jobs = iter(jobs)
        self.retry: List[str] = []

    def __iter__(self):
        return self

    def __next__(self) -> str:
        for key in self.jobs:
            return key
        if self.retry:
            return self.retry.pop()
        raise StopIteration


async def run_checks(
    jobs: List[str],
    checker: Checker,
    opts: RunOptions,
    dashboard: CheckDashboard,
    writer: ResultWriter,
    geo: GeoResolver,
    live_factory: Callable,
    watch: Optional[JudgeWatch] = None,
) -> CheckRun:
    """Prüft `jobs` mit `opts.concurrency` parallelen Workern bis alles durch, das Ziel erreicht
    oder Strg+C gedrückt ist.

    Mit `watch` wird das Prüfziel überwacht: Fällt es aus, werden die Prüfungen seit der letzten
    erfolgreichen Kontrolle wiederholt und zählen nicht für die Quellen-Statistik."""
    loop = asyncio.get_running_loop()
    stats = dashboard.s
    filters, details, want = opts.filters, opts.details, opts.want
    run = CheckRun()
    written: Set[str] = set()
    enriched: Set[str] = set()  # Treffer mit abgeschlossener Detailprüfung (HTTPS kann dabei offen bleiben)
    by_exit_ip: Dict[str, List[CheckResult]] = {}
    pending = JobQueue(jobs)  # alle Worker ziehen aus derselben Queue – in asyncio ohne Lock sicher

    # Prüfziel-Ausfälle: Jede Prüfung merkt sich, mit welchem Ziel ("Generation") und als wievielte sie begann.
    # Beim Wechsel wird die alte Generation ab der letzten guten Kontrolle verdächtig – Fehlschläge
    # daraus werden wiederholt, auch solche, die erst nach dem Wechsel fertig werden. Treffer sind
    # nie verdächtig (der Proxy hat ja funktioniert), so wird jede Prüfung genau einmal gewertet.
    generation = 0
    # Reihenfolge statt Uhrzeit: jede Prüfung bekommt beim Start eine laufende Nummer. Die Uhr der Event-Loop
    # ist unter Windows nur auf ~15 ms genau – zwei Ereignisse bekämen dort leicht denselben Zeitstempel.
    started_count = 0
    last_ok = 0  # so viele Prüfungen hatten bei der letzten guten Kontrolle begonnen (0 = Lauf-Start)
    suspect_since: Dict[int, int] = {}       # abgelöste Generation -> Prüfungen ab dieser Nummer verdächtig
    recent_failures: List[Tuple[int, int, str]] = []  # Fehlschläge seit der letzten guten Kontrolle

    def is_suspect(gen: int, started: int) -> bool:
        return gen in suspect_since and started > suspect_since[gen]

    def requeue(keys: List[str]) -> None:
        pending.retry.extend(keys)
        run.rechecked += len(keys)
        dashboard.add_rechecks(keys)

    def judge_ok() -> None:
        nonlocal last_ok
        last_ok = started_count
        recent_failures.clear()

    def judge_switched(old, new) -> None:
        nonlocal generation, last_ok
        suspect_since[generation] = last_ok
        generation += 1
        last_ok = started_count  # das neue Ziel wurde gerade erfolgreich geprüft – ab hier die Basislinie
        failed = {key for gen, started, key in recent_failures if is_suspect(gen, started)}
        recent_failures.clear()
        if failed:
            run.checked[:] = [k for k in run.checked if k not in failed]
        requeue(sorted(failed))
        run.judge_switches.append(f"{old.judge.host} → {new.judge.host}")
        dashboard.judge_changed(new.judge.host)

    if watch:
        watch.on_ok, watch.on_switch = judge_ok, judge_switched
    all_workers: Optional[asyncio.Future] = None

    def consider(r: CheckResult) -> None:
        """Live-Datei & Zielzähler, sobald alle für die Filter nötigen Infos da sind."""
        if r.key in written or (details and r.key not in enriched):
            return
        if filters.countries and not r.country:
            return  # Land kommt noch – on_country ruft erneut auf
        if filters.accepts(r):
            written.add(r.key)
            stats.passing += 1
            writer.add_live(r)
            if want and stats.passing >= want and all_workers and not all_workers.done():
                run.reached_goal = True
                all_workers.cancel()

    def on_country(ip: str, cc: str) -> None:
        for r in by_exit_ip.get(ip, ()):
            if not r.country:
                r.country = cc
                stats.countries[cc] += 1
                consider(r)

    geo.on_resolved = on_country
    geo_task = asyncio.ensure_future(geo.run())
    watch_task = asyncio.ensure_future(watch.run()) if watch else None

    async def worker() -> None:
        nonlocal started_count
        for key in pending:
            started_count += 1
            gen, started = generation, started_count
            r = await checker.check(key)
            stats.add_checked(key.split(" ", 1)[0])
            dashboard.advance()
            if r is None and is_suspect(gen, started):
                requeue([key])  # erst nach dem Wechsel fertig geworden – trotzdem ein Opfer des Ausfalls
                continue
            run.checked.append(key)
            if r is None:
                if watch:
                    recent_failures.append((gen, started, key))
                continue
            # Zweite, unabhängige Anfrage – Honeypots bestehen die erste Prüfung oft zufällig
            if not await checker.confirm(r):
                stats.fakes += 1
                continue
            # Dritte Anfrage: kommt eine bekannte Seite unverändert an? Sonst schleust der Proxy etwas ein
            if await checker.tampers(r):
                stats.tampered += 1
                continue
            run.results.append(r)
            run.working.add(key)
            by_exit_ip.setdefault(r.exit_ip, []).append(r)
            r.country = geo.request(r.exit_ip)
            if r.country:
                stats.countries[r.country] += 1
            stats.add_working(r)
            if details:
                # HTTPS-Test nur, wenn der Proxy die Filter überhaupt noch erfüllen kann
                if filters.may_pass(r):
                    await checker.enrich(r)
                    enriched.add(r.key)
                    stats.add_details(r)
                else:
                    stats.details_saved += 1
            consider(r)

    with live_factory(dashboard):
        workers = [asyncio.ensure_future(worker()) for _ in range(min(opts.concurrency, len(jobs)))]
        all_workers = asyncio.gather(*workers)
        # Strg+C bricht sauber ab, damit die Ergebnisse trotzdem gespeichert werden (auch unter Windows)
        with on_interrupt(loop, all_workers.cancel):
            try:
                await all_workers
            except asyncio.CancelledError:
                run.interrupted = not run.reached_goal

    if watch_task:
        watch_task.cancel()
    # Offene Länder-Abfragen noch abwarten (höchstens kurz)
    geo.stop()
    if geo.pending and not geo.failed:
        message = f"[bold {ACCENT}]Ermittle Länder für {fmt(len(geo.pending))} Exit-IPs …"
        with widgets.console.status(message, spinner="dots"), contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(geo_task), 30)
    geo_task.cancel()
    return run
