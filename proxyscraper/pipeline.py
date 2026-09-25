"""Flow: assemble sources, load & parse in parallel, prioritize, check."""

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
from .asndb import ProviderLookup
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
# parse small lists directly – the detour through another process costs more than it saves
INLINE_PARSE_BYTES = 256 * 1024
DOWNLOAD_CONCURRENCY = 64


# --------------------------------------------------------------------------- #
# Sources
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
    """Curated + meta + discovered sources, minus the ones learned to be bad."""
    sources, meta = srcs.load_source_file()
    n_curated = len(sources)

    age = srcs.discovered_age_days()
    due = not opts.no_discover and (age is None or age > AUTO_DISCOVER_AFTER_DAYS)
    # asking gh for a token takes up to 5 s – only when discovery can actually run, and off the event loop
    token = await asyncio.to_thread(srcs.github_token) if (opts.discover or due) else None
    run_discovery = opts.discover or (due and token is not None)
    if run_discovery:
        max_repos = opts.discover_repos if token else min(opts.discover_repos, 40)
        with widgets.console.status(f"[bold {ACCENT}]Searching GitHub for new proxy lists …", spinner="dots") as status:
            found = await srcs.discover_github(
                http_get, token, max_repos,
                on_progress=lambda msg: status.update(f"[bold {ACCENT}]GitHub-Discovery:[/] {msg}"),
            )
        if found:
            srcs.save_discovered(found)
    discovered = srcs.load_discovered()

    with widgets.console.status(f"[bold {ACCENT}]Loading meta sources …", spinner="dots"):
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
            reason = quality.skip_now(url)
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
    # proxy key -> indices of the sources that list it (for priority and statistics)
    index: Dict[str, List[int]] = field(default_factory=dict)
    ok_sources: int = 0


async def scrape(sources: Dict[str, str], types, quality: srcs.SourceStats, view: CollectView,
                 cache: Optional[FetchCache] = None) -> ScrapeResult:
    """Loads every source and parses large lists in parallel on all CPU cores.

    That keeps the event loop free for more downloads instead of working through regexes for minutes.
    With the cache, unchanged lists are skipped via ETag (see fetchcache.py).
    """
    res = ScrapeResult(list(sources))
    cache = cache or FetchCache(enabled=False)
    # always parse every type, filtering only happens when sorting them in: the cache stores all types, and
    # the statistics must be able to tell "no proxies at all" from "none of the requested types"
    parse_types = PROXY_TYPES
    prefixes = tuple(f"{t} " for t in types)
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    index = res.index

    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:

        async def download(url: str):
            """-> (data, keys from the cache). Exactly one of the two is set."""
            conditional = cache.conditional_headers(url, sources[url])
            async with sem:
                status, headers, body = await http_request(url, timeout=30, headers=conditional or None)
            if status == 304 and conditional:
                cached = cache.load(url)
                if cached is not None:
                    return None, headers, cached
                async with sem:  # cache file broken -> just load it again
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
            except Exception:  # source unreachable/broken – counts as a failure in the statistics
                pass
            n = parsed = 0
            if keys:
                parsed = keys.count("\n") + 1  # every type, also the ones this run doesn't want
                for key in keys.split("\n"):
                    if not key.startswith(prefixes):
                        continue
                    owners = index.get(key)
                    if owners is None:
                        index[key] = [i]
                    else:
                        owners.append(i)
                    n += 1
            quality.record_fetch(url, data, n, unchanged=unchanged, parsed=parsed)
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
    """Order of checking: known working proxies first, then by quality of the sources.

    Within the same source quality, proxies that appear in more lists win.
    """
    wanted = set(types)
    known = [k for k in history.ranked_keys() if split_key(k)[0] in wanted]
    known_set = set(known)

    scores = [quality.score(u) for u in res.urls]
    keys = [k for k in res.index if k not in known_set]
    random.shuffle(keys)  # shuffle real ties so every type makes progress
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
    """Attribute results to the sources -> url -> (checked, working)."""
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
# Checking
# --------------------------------------------------------------------------- #

@dataclass
class CheckRun:
    results: List[CheckResult] = field(default_factory=list)
    checked: List[str] = field(default_factory=list)
    working: Set[str] = field(default_factory=set)
    interrupted: bool = False
    reached_goal: bool = False
    judge_switches: List[str] = field(default_factory=list)  # "old → new"
    rechecked: int = 0  # checks that were repeated because a check target went down


class JobQueue:
    """Iterator over the jobs that still accepts stragglers after running empty.

    A generator would be exhausted forever after the first StopIteration – a proxy that a still
    running worker puts back after a check-target switch would then never be checked again."""

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
    providers: Optional[ProviderLookup] = None,
) -> CheckRun:
    """Checks `jobs` with `opts.concurrency` parallel workers until everything is done, the goal is
    reached or Ctrl+C is pressed.

    With `watch` the check target is monitored: if it goes down, the checks since the last successful
    probe are repeated and don't count for the source statistics."""
    loop = asyncio.get_running_loop()
    stats = dashboard.s
    filters, details, want = opts.filters, opts.details, opts.want
    run = CheckRun()
    written: Set[str] = set()
    enriched: Set[str] = set()  # hits with a finished detail check (HTTPS may stay open)
    by_exit_ip: Dict[str, List[CheckResult]] = {}
    pending = JobQueue(jobs)  # all workers pull from the same queue – safe in asyncio without a lock

    # Check target outages: every check remembers which target ("generation") it started with and its number.
    # On a switch the old generation becomes suspicious from the last good probe on – failures from it
    # are repeated, including those that only finish after the switch. Hits are never suspicious
    # (the proxy did work), so every check is counted exactly once.
    generation = 0
    # Order instead of clock time: every check gets a running number when it starts. The event loop clock
    # is only accurate to ~15 ms on Windows – two events could easily get the same timestamp there.
    started_count = 0
    last_ok = 0  # this many checks had started at the last good probe (0 = start of the run)
    suspect_since: Dict[int, int] = {}       # replaced generation -> checks from this number on are suspicious
    recent_failures: List[Tuple[int, int, str]] = []  # failures since the last good probe

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
        last_ok = started_count  # the new target was just probed successfully – the baseline from here on
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
        """Live file & goal counter, as soon as all the info the filters need is there."""
        if r.key in written or (details and r.key not in enriched):
            return
        if filters.countries and not r.country:
            return  # country still coming – on_country calls again
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
                requeue([key])  # only finished after the switch – still a victim of the outage
                continue
            if r is None:
                run.checked.append(key)
                if watch:
                    recent_failures.append((gen, started, key))
                continue
            # A hit only counts as checked once the verdict is in: a worker cancelled during the next requests
            # (--want reached, Ctrl+C) must not record a proxy that just worked as a failure.
            # second, independent request – honeypots often pass the first check by chance
            if not await checker.confirm(r):
                run.checked.append(key)
                stats.fakes += 1
                continue
            # third request: does a known page arrive unchanged? Otherwise the proxy injects something
            if await checker.tampers(r):
                run.checked.append(key)
                stats.tampered += 1
                continue
            if providers:
                providers.annotate(r)
            run.checked.append(key)
            run.results.append(r)
            run.working.add(key)
            by_exit_ip.setdefault(r.exit_ip, []).append(r)
            r.country = geo.request(r.exit_ip)
            if r.country:
                stats.countries[r.country] += 1
            stats.add_working(r)
            if details:
                # HTTPS test only if the proxy can still pass the filters at all
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
        # Ctrl+C stops cleanly so the results still get saved (on Windows too)
        with on_interrupt(loop, all_workers.cancel):
            try:
                await all_workers
            except asyncio.CancelledError:
                run.interrupted = not run.reached_goal

    if watch_task:
        watch_task.cancel()
    # wait for open country lookups (briefly at most)
    geo.stop()
    if geo.pending and not geo.failed:
        message = f"[bold {ACCENT}]Looking up countries for {fmt(len(geo.pending))} exit IPs …"
        with widgets.console.status(message, spinner="dots"), contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(geo_task), 30)
    geo_task.cancel()
    return run
