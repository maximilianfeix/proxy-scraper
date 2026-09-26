"""One complete run in clear phases: network → jobs → check → learn & report."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
import sys
import tempfile
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Tuple

from rich.live import Live
from rich.text import Text

from . import sources as srcs
from .asndb import AsnDB, ProviderLookup, load_asn_db
from .asndb import is_current as asn_is_current
from .blocklist import Blocklist
from .checker import (
    CONFIRM_HOST,
    CONFIRM_PORT,
    DETAIL_CONNECTIONS,
    JUDGE_HOST,
    Checker,
    CheckResult,
    integrity_reference,
    probe_confirm_target,
)
from .compat import on_interrupt, raise_fd_limit
from .fetchcache import FetchCache
from .geo import GeoResolver
from .geodb import CountryDB, is_current, load_country_db
from .handshake import parse_endpoint
from .history import ProxyHistory
from .judges import JudgeProbe, JudgeWatch, rank_judges
from .netio import INSECURE_HOSTS, http_get
from .options import STDOUT, RunOptions
from .output import ResultWriter, latest_results
from .parsing import PROXY_TYPES, parse_keys, split_key
from .paths import is_checkout
from .pipeline import (
    CheckRun,
    ScrapeResult,
    attribute_results,
    best_sources,
    collect_sources,
    prioritize,
    run_checks,
    scrape,
)
from .publish import RAW_BASE
from .server import ProxyPool, RotatingServer
from .targets import Target, parse_target
from .ui import (
    ACCENT,
    BAD,
    BLOCKED_HIT_RATE,
    GOOD,
    MUTED,
    WARN,
    CheckDashboard,
    CollectView,
    LiveStats,
    banner,
    fmt,
    fmt_duration,
    info,
    note,
    pct,
    render_summary,
    section,
    section_end,
    widgets,
)
from .ui.serve import ServeDashboard
from .ui.widgets import shown_proxy

OWN_IP_URLS = (
    f"https://{JUDGE_HOST}/",       # HTTPS first: relays and corporate proxies don't redirect it
    "https://api.ipify.org/",
    f"http://{JUDGE_HOST}/",        # port 80 may take a different route (a different IP)
)


async def get_own_ips() -> List[str]:
    """Every IP you are visible under from the outside – the most important one first."""

    async def one(url: str) -> str:
        try:
            ip = (await http_get(url, timeout=6)).strip().decode("ascii", "ignore")
            ipaddress.IPv4Address(ip)
            return ip
        except Exception:  # service unreachable -> the next one counts
            return ""

    ips = await asyncio.gather(*(one(u) for u in OWN_IP_URLS))
    return list(dict.fromkeys(ip for ip in ips if ip))


async def confirm_target() -> Optional[str]:
    """IP of the confirmation target – only if exactly this IP answers the way the confirmation expects."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(CONFIRM_HOST, CONFIRM_PORT, family=socket.AF_INET)
    except OSError:  # can't be resolved -> continue without confirmation, with a note
        return None
    ip = infos[0][4][0]
    return ip if await probe_confirm_target(ip, timeout=8) else None


def load_recheck_jobs(target: str, types, history: ProxyHistory) -> List[str]:
    """--recheck: a file, otherwise the last run plus history."""
    if target:
        lines = Path(target).expanduser().read_text(encoding="utf-8").splitlines()
        # lines without type:// in files like http.txt take the type from the file name
        default = next((t for t in PROXY_TYPES if t in Path(target).name.lower()), None)
        keys = parse_keys(lines, default)
    else:
        keys = parse_keys(latest_results()) + history.ranked_keys()
        keys = list(dict.fromkeys(keys))
    return [k for k in keys if split_key(k)[0] in types]


LIVE = "live"  # --recheck live: the public live list as the starting point
REFILL_CONCURRENCY = 500  # checks at once during --serve-refill, so the running server stays responsive
LIVE_URL = f"{RAW_BASE}/all.txt"


async def load_live_jobs(types, history: ProxyHistory, fetch=http_get) -> List[str]:
    """Load the live list (only addresses that worked in the last GitHub Actions run) plus your own hits
    from the history – everything is then checked locally, from your own network."""
    try:
        text = (await fetch(LIVE_URL, timeout=30)).decode("utf-8", "replace")
    except Exception:
        note("Live list unreachable – using the last run and history instead.", WARN, "⚠")
        return load_recheck_jobs("", types, history)
    keys = list(dict.fromkeys(parse_keys(text.splitlines()) + history.ranked_keys()))
    return [k for k in keys if split_key(k)[0] in types]


def is_network_blocked(stats: LiveStats) -> bool:
    """If (almost) nothing gets through, a firewall is probably blocking proxy connections.

    Fake proxies count too: they pass the basic check, so the connection works – a network full of
    honeypots is not a blocked network, and the run should still be learned from.
    """
    reached = stats.found + stats.fakes + stats.tampered
    return stats.checked >= 1000 and reached < stats.checked * BLOCKED_HIT_RATE


def next_steps(opts: RunOptions, kept: List[CheckResult]) -> List[Tuple[str, str]]:
    """Ready-made commands for what people usually do next after a run."""
    program = "python3 proxy_scraper.py" if is_checkout() else "proxy-scraper"
    steps: List[Tuple[str, str]] = []
    if kept:
        # only suggest HTTPS if the proxy passed the HTTPS test – otherwise the command fails
        secure = [r for r in kept if r.https]
        pool = secure or kept
        # prefer proxies without a login – the command ends up in the terminal, no password belongs there
        best = min([r for r in pool if "@" not in r.proxy] or pool, key=lambda r: r.latency)
        scheme = "socks5h" if best.ptype == "socks5" else best.ptype
        target = "https://api.ipify.org" if best.https else "http://api.ipify.org"
        steps.append(("Test the fastest", f"curl -x {scheme}://{shown_proxy(best.proxy)} {target}"))
        if not opts.serve:
            steps.append(("As a proxy server", f"{program} --recheck --serve"))
    steps.append(("Recheck later", f"{program} --recheck"))
    return steps


def pool_recheck(checker: Checker):
    """Recheck for the proxy server's disabled proxies: the normal check, but bypassing the cache."""
    async def recheck(result: CheckResult) -> bool:
        # the checker remembers unreachable addresses for the rest of the run – exactly those should be
        # tried again here
        checker.unreachable.discard(parse_endpoint(result.proxy).address)
        return await checker.check(result.key) is not None
    return recheck


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class Run:
    def __init__(self, opts: RunOptions, show_banner: bool = True):
        self.opts = opts
        self.show_banner = show_banner
        self.started = time.perf_counter()
        self.quality = srcs.SourceStats()
        self.history = ProxyHistory()
        self.scraped: Optional[ScrapeResult] = None
        self.judges: List[JudgeProbe] = []  # reachable check targets, fastest first
        self.integrity: Optional[bytes] = None  # hash of the reference page (see Checker.tampers)
        self.checker: Optional[Checker] = None
        self.kept: List[CheckResult] = []  # hits that pass every filter (for the Python API)
        self.confirm_ip: Optional[str] = None
        self.targets: List[Tuple[Target, str]] = []
        self.own_ips: List[str] = []
        self.blocklist: Optional[Blocklist] = None

    async def execute(self) -> int:
        if self.show_banner:
            widgets.console.print(banner())
        section("Setup")
        try:
            with widgets.console.status("Checking the network …", spinner="dots", spinner_style=ACCENT):
                ready = await self.prepare_network()
            if not ready:
                return 1
            self.show_mode()
            jobs = await self.gather_jobs()
            if not jobs:
                note("No proxies to check.", BAD, "✘")
                return 1
        finally:
            section_end()
        await self.check_and_report(jobs)
        return 0

    # ------------------------------------------------------------------ phase 0: network

    async def prepare_network(self) -> bool:
        blocklist = Blocklist() if not self.opts.no_dnsbl else None
        self.judges, self.own_ips, _ = await asyncio.gather(
            rank_judges(), get_own_ips(), blocklist.probe() if blocklist else asyncio.sleep(0))
        if blocklist and blocklist.usable:
            self.blocklist = blocklist
        if not self.judges:
            note("No check target reachable (checkip.amazonaws.com, ifconfig.me, …) – check your internet connection.",
                 BAD, "✘")
            return False
        if not self.own_ips:  # the usual services for your own IP are gone – the check targets have seen it
            # IPv4 only – the checker compares against IPv4 exit IPs; an IPv6 (e.g. iCloud Private Relay) never
            # matches and would only swallow the "own IP unknown" warning
            self.own_ips = list(dict.fromkeys(j.seen_ip for j in self.judges if j.seen_ip and "." in j.seen_ip))
        ips = self.own_ips
        info("Your IP", Text.assemble(
            (ips[0], "bold") if ips else ("unknown", WARN),
            (f"  (on port 80 also {', '.join(ips[1:])})" if len(ips) > 1 else "", MUTED),
        ))
        if not await self.resolve_targets():
            return False
        self.confirm_ip = await confirm_target()
        if self.confirm_ip:  # reference page for the check against modified content
            self.integrity = await integrity_reference(timeout=8)
        best, reserve = self.judges[0], [j.judge.host for j in self.judges[1:]]
        info("Check target", Text.assemble(
            (f"{best.judge.host} ({best.ip}, {best.latency} ms)", MUTED),
            (f"  ·  fallback: {', '.join(reserve)}", MUTED) if reserve else "",
            (f"  ·  confirmed via {CONFIRM_HOST}", MUTED) if self.confirm_ip else "",
        ))
        if self.confirm_ip and self.integrity is None:
            note(f"Reference page from {CONFIRM_HOST} unreachable – proxies that modify content "
                 "won't be detected in this run.")
        if not self.confirm_ip:
            note(f"{CONFIRM_HOST} unreachable – without a second confirmation fake proxies (honeypots) "
                 "can slip through, and anonymity stays unknown.")
        if not ips:
            note("Own IP unknown – transparent proxies (they reveal your IP) won't be filtered out.")
        if blocklist and not blocklist.usable:
            note("SpamCop doesn't answer through your DNS resolver (large public resolvers are refused) – "
                 "blocklist info is skipped" + (", so --no-blocklisted can't filter anything." if
                                                self.opts.filters.no_blocklisted else "."), MUTED, "ℹ")
        return True

    async def resolve_targets(self) -> bool:
        """Resolve the target sites once – SOCKS4 needs IPs, and a typo should show up right away."""
        loop = asyncio.get_running_loop()
        for url in self.opts.filters.targets:
            target = parse_target(url)
            try:
                infos = await loop.getaddrinfo(target.host, target.port, family=socket.AF_INET)
            except OSError:
                note(f"Target site {target.host} can't be resolved – a typo?", BAD, "✘")
                return False
            self.targets.append((target, infos[0][4][0]))
        if self.targets:
            info("Target sites", ", ".join(t.label for t, _ in self.targets))
        return True

    def show_mode(self) -> None:
        opts = self.opts
        modes = ["with HTTPS test" if opts.details else "without HTTPS test (--fast)"]
        modes.append("countries" if opts.geo else "no countries")
        if opts.filters.active:
            modes.append(f"filter: {opts.filters.describe()}")
        if opts.want:
            modes.append(f"stops at {fmt(opts.want)} hits")
        if opts.check_timeout < opts.timeout:
            modes.append(f"timeout {opts.check_timeout:g} s thanks to the latency limit")
        info("Mode", " · ".join(modes))

    # ------------------------------------------------------------------ phase 1+2: jobs

    async def gather_jobs(self) -> List[str]:
        opts = self.opts
        if opts.recheck == LIVE:
            jobs = await load_live_jobs(opts.types, self.history)
            info("Recheck", f"{fmt(len(jobs))} proxies from the live list (checked every hour by GitHub Actions)")
        elif opts.recheck is not None:
            try:
                jobs = load_recheck_jobs(opts.recheck, opts.types, self.history)
            except (OSError, UnicodeDecodeError) as e:
                reason = e.strerror if isinstance(e, OSError) and e.strerror else "not a text file"
                note(f"Can't read {opts.recheck}: {reason}.", BAD, "✘")
                return []
            info("Recheck", f"{fmt(len(jobs))} proxies from {opts.recheck or 'the last run + history'}")
        else:
            jobs = await self._scrape_jobs()

        known = sum(1 for k in jobs if k in self.history) if len(self.history) else 0
        if known:
            info("History", f"{fmt(known)} proxies that worked before are checked first")
        if opts.limit:
            jobs = jobs[: opts.limit]
            info("Limit", f"checking the {fmt(len(jobs))} most promising")
        return jobs

    async def _scrape_jobs(self) -> List[str]:
        plan = await collect_sources(self.opts, self.quality)
        info("Sources", Text.assemble(
            (fmt(len(plan.sources)), f"bold {ACCENT}"), " active  ",
            (f"({fmt(plan.n_curated)} curated · {fmt(plan.n_meta)} from {plan.meta_ok}/{plan.meta_total} "
             f"meta lists · {fmt(plan.n_discovered)} discovered)", MUTED),
        ))
        if plan.discovery_ran and not plan.discovery_token:
            note("GitHub discovery is limited without a token – run `gh auth login` or set GITHUB_TOKEN.",
                 MUTED, "ℹ")
        if plan.skipped:
            parts = ", ".join(f"{n} {reason}" for reason, n in plan.skipped.most_common())
            info("Skipped", Text.assemble(parts, ("  (force all: --all-sources)", MUTED)))

        t0 = time.perf_counter()
        view = CollectView(len(plan.sources), self.started)
        with Live(view, console=widgets.console, refresh_per_second=10, transient=True):
            cache = FetchCache(enabled=not self.opts.no_cache)
            self.scraped = await scrape(plan.sources, self.opts.types, self.quality, view, cache)
        self.quality.save()
        cache.save()
        res = self.scraped
        info("Collected", Text.assemble(
            (fmt(len(res.index)), f"bold {GOOD}"), " unique proxies from ",
            f"{res.ok_sources}/{len(plan.sources)} sources",
            (f"  ({view.bytes / 2**20:.0f} MB in {fmt_duration(time.perf_counter() - t0)}"
             + (f", {view.cached} unchanged from the cache" if view.cached else "") + ")", MUTED),
        ))
        if INSECURE_HOSTS:
            hosts = sorted(INSECURE_HOSTS)
            note(f"Certificate could not be verified (TLS inspection on this network?), loaded anyway: "
                 f"{', '.join(hosts[:4])}{' …' if len(hosts) > 4 else ''}", MUTED, "ℹ")
        return prioritize(res, self.quality, self.history, self.opts.types)

    # ------------------------------------------------------------------ phase 3+4: check, learn, report

    async def check_and_report(self, jobs: List[str]) -> None:
        # workers + capped detail connections + headroom for sources, geo and the like
        fd = raise_fd_limit(self.opts.concurrency + DETAIL_CONNECTIONS + 512)
        opts = replace(self.opts, concurrency=min(self.opts.concurrency, max(fd - DETAIL_CONNECTIONS - 256, 64)))

        to_stdout = opts.output == STDOUT
        writer = ResultWriter(extra_file=Path(opts.output) if opts.output and not to_stdout else None,
                              exports=opts.exports, stdout=sys.stdout if to_stdout else None)
        stats = LiveStats(Counter(split_key(k)[0] for k in jobs))
        dashboard = CheckDashboard(stats, writer.live_path, opts.concurrency, opts.details,
                                   opts.filters.describe(), opts.want, opts.filters.targets)
        judge = self.judges[0]
        checker = Checker(judge.ip, self.own_ips, opts.check_timeout, opts.check_connect_timeout,
                          self.confirm_ip, detail_timeout=opts.timeout,
                          detail_connect_timeout=opts.connect_timeout, targets=self.targets,
                          https_test=not opts.fast or opts.filters.https_only, judge=judge.judge,
                          integrity_reference=self.integrity)
        self.checker = checker  # for the proxy server: rechecking disabled proxies
        watch = JudgeWatch(self.judges, lambda new: checker.use_judge(new.judge, new.ip))
        dashboard.judge = judge.judge.host
        # country database straight from data/ (2 ms); if it's old or missing, reload it in the background –
        # until then ip-api.com takes over, nobody waits for the download
        country_db = CountryDB.load() if opts.geo else None
        geo = GeoResolver(enabled=opts.geo, offline=country_db)
        refresh = None
        if opts.geo and not is_current(country_db):
            refresh = asyncio.ensure_future(self.refresh_country_db(geo))
        # providers of the exit IPs the same way: straight from data/, old or missing -> reload in the background.
        # Independent of --no-geo – that only concerns countries, providers come from the file anyway.
        providers = ProviderLookup(AsnDB.load())
        providers_refresh = None
        if not asn_is_current(providers.db):
            providers_refresh = asyncio.ensure_future(self.refresh_asn_db(providers))
            if opts.filters.no_datacenter and providers.db is None:
                # explicitly without datacenters, but no database at all yet: load it before checking –
                # otherwise unknown providers would pass as "not a datacenter" and --want would stop too early
                with widgets.console.status("Loading the provider database (DB-IP) …", spinner="dots"), \
                        contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(providers_refresh), 90)
        widgets.console.print()
        run = await run_checks(
            jobs, checker, opts, dashboard, writer, geo,
            live_factory=lambda renderable: Live(renderable, console=widgets.console, refresh_per_second=6),
            watch=watch,
            providers=providers,
            blocklist=self.blocklist,
        )

        if refresh and not refresh.done():
            refresh.cancel()  # country download still running – next run then (ip-api took over)
        if providers_refresh and not providers_refresh.done():
            # provider database still loading (first run or new month): wait briefly and fill in afterwards –
            # otherwise the files lack providers and --no-datacenter would let datacenters through
            with widgets.console.status("Loading the provider database (DB-IP) …", spinner="dots"), \
                    contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(providers_refresh), 30)
            if not providers_refresh.done():
                providers_refresh.cancel()  # takes too long – next run then
        if providers.db:
            for r in run.results:
                if not r.asn:
                    providers.annotate(r)
                    if r.hosting:
                        stats.hosting += 1  # otherwise dashboard and note would show too few datacenters
        kept = [r for r in run.results if opts.filters.accepts(r)]
        self.kept = kept
        files = writer.finalize(kept)
        network_blocked = is_network_blocked(stats)
        per_source = self.learn(run, network_blocked)
        geo.save()

        render_summary(stats, run.results, kept, best_sources(per_source), files, opts.details,
                       opts.filters.describe(), next_steps(opts, kept))
        self.final_notes(run, stats, kept, geo, network_blocked)
        if opts.serve:
            await self.serve(kept)

    async def serve(self, proxies: List[CheckResult]) -> None:
        """Serve the proxies found as a local rotating proxy server until Ctrl+C."""
        if not proxies:
            note("No matching proxy found – the proxy server doesn't start.", BAD, "✘")
            return
        pool = ProxyPool(proxies, strategy=self.opts.rotate, sticky_seconds=self.opts.sticky)
        server = RotatingServer(pool, host=self.opts.serve_host, port=self.opts.serve, timeout=self.opts.timeout,
                                password=self.opts.serve_password)
        if not is_loopback(self.opts.serve_host) and not self.opts.serve_password:
            note(f"The proxy server listens on {self.opts.serve_host} – without a password. Anyone who can reach "
                 "it can use it. Set PROXY_SCRAPER_SERVE_PASSWORD, or keep it behind a firewall "
                 "or in a container with -p 127.0.0.1:…", WARN, "⚠")
        try:
            await server.start()
        except OSError as e:
            note(f"Port {self.opts.serve} is not available ({e.strerror or e}) – pick another one with --serve PORT.",
                 BAD, "✘")
            return
        stop = asyncio.Event()
        widgets.console.print()
        fresh = refills = None
        if self.checker:  # recheck disabled proxies every 5 minutes and bring them back if they work
            fresh = asyncio.ensure_future(server.keep_fresh(pool_recheck(self.checker)))
            if self.opts.serve_refill:
                refills = asyncio.ensure_future(self.keep_refilling(server, self.opts.serve_refill * 3600))
        try:
            with on_interrupt(asyncio.get_running_loop(), stop.set), \
                    Live(ServeDashboard(server), console=widgets.console, refresh_per_second=4):
                await stop.wait()
        finally:
            for task in (fresh, refills):
                if task:
                    task.cancel()
            await server.close()
        st = server.stats
        note(f"Proxy server stopped – {fmt(st.requests)} requests, {fmt(st.ok)} successful.", GOOD, "✔")

    async def keep_refilling(self, server: RotatingServer, interval: float) -> None:
        """--serve-refill: every `interval` seconds check fresh candidates and merge the hits into the pool."""
        while True:
            await asyncio.sleep(interval)
            try:
                server.refilled += await self.refill(server.pool)
            except Exception as e:  # noqa: BLE001 – the server keeps running with what it has
                note(f"Refill failed ({e.__class__.__name__}: {e}) – trying again next time.", WARN, "⚠")
            server.last_refill = time.time()

    async def refill(self, pool: ProxyPool) -> int:
        """One refill: the same checks and filters as the first run, quietly in the background. -> proxies added."""
        opts = replace(self.opts, concurrency=min(self.opts.concurrency, REFILL_CONCURRENCY))
        if opts.recheck == LIVE:
            jobs = await load_live_jobs(opts.types, self.history)
        else:
            jobs = load_recheck_jobs("", opts.types, self.history)
        serving = {e.result.key for e in pool.usable}  # working right now – no need to check them again
        jobs = [k for k in jobs if k not in serving]
        if not jobs:
            return 0
        # the check target picked at startup may be gone hours later – rank again and watch it like the first run
        judges = await rank_judges()
        if not judges:
            return 0
        checker = self.checker
        checker.use_judge(judges[0].judge, judges[0].ip)
        watch = JudgeWatch(judges, lambda new: checker.use_judge(new.judge, new.ip))
        checker.unreachable.clear()  # hours later, addresses that were down may be back
        stats = LiveStats(Counter(split_key(k)[0] for k in jobs))
        geo = GeoResolver(enabled=opts.geo, offline=CountryDB.load() if opts.geo else None)
        # a scratch folder: "latest" stays the full run, not the handful of new hits from this round
        with tempfile.TemporaryDirectory(prefix="proxy-scraper-refill-") as scratch:
            writer = ResultWriter(run_dir=Path(scratch))
            dashboard = CheckDashboard(stats, writer.live_path, opts.concurrency, opts.details,
                                       opts.filters.describe(), opts.want, opts.filters.targets)
            try:
                run = await run_checks(jobs, checker, opts, dashboard, writer, geo,
                                       live_factory=lambda _view: contextlib.nullcontext(), watch=watch,
                                       providers=ProviderLookup(AsnDB.load()), blocklist=self.blocklist, quiet=True)
            finally:
                writer.close()
        kept = [r for r in run.results if opts.filters.accepts(r)]
        blocked = is_network_blocked(stats)
        self.learn(run, blocked, sources=False)  # the source ranking only learns from full scans
        geo.save()
        return 0 if blocked else pool.merge(kept)  # a blocked network proves nothing about the pool

    @staticmethod
    async def refresh_asn_db(providers: ProviderLookup) -> None:
        try:
            db = await load_asn_db()
        except Exception:
            return
        if db is not None:
            providers.db = db

    @staticmethod
    async def refresh_country_db(geo: GeoResolver) -> None:
        """Load a new country database and use it right away – errors don't matter, ip-api stays in charge."""
        try:
            db = await load_country_db()
        except Exception:
            return
        if db is not None:
            geo.use_offline(db)

    def learn(self, run: CheckRun, network_blocked: bool, sources: bool = True):
        """Update source statistics and history – on a blocked network only the hits."""
        per_source = attribute_results(self.scraped, run.checked, run.working) if self.scraped and sources else {}
        if not network_blocked:
            # on a blocked network every source and known proxy would wrongly count as "dead"
            self.quality.record_checks(per_source)
            for key in run.checked:
                if key not in run.working:
                    self.history.record_fail(key)
        for r in run.results:
            self.history.record_ok(r.key, r.latency, r.exit_ip, country=r.country,
                                   anonymity=r.anonymity, https=r.https)
        self.history.prune()
        self.history.save()
        self.quality.save()
        return per_source

    def final_notes(self, run: CheckRun, stats: LiveStats, kept, geo: GeoResolver, network_blocked: bool) -> None:
        opts = self.opts
        if network_blocked:
            note(
                f"[bold]{fmt(stats.checked)} proxies checked, only {fmt(stats.found)} work.[/] "
                "Your network (company or school firewall) is probably blocking proxy connections – try "
                f"another network, e.g. a phone hotspot. [{MUTED}]Statistics and history were not "
                "downgraded for this run.[/]"
            )
        if opts.geo and geo.failed:
            if geo.offline:
                note("ip-api.com unreachable – addresses that aren't in the DB-IP database "
                     "stay without a country.", MUTED, "ℹ")
            else:
                note("Country database and ip-api.com unreachable – countries are missing.", MUTED, "ℹ")
        if opts.filters.countries and not kept and run.results:
            note("No hit in the requested country – loosen the filter or let it run longer.", MUTED, "ℹ")
        if run.judge_switches:
            note(f"Check target went down, switched: {', '.join(run.judge_switches)}. {fmt(run.rechecked)} proxies "
                 "were checked again and don't count for the source statistics.", WARN, "⚠")
        if stats.tampered:
            note(f"{fmt(stats.tampered)} proxies modified a test page (usually by injecting scripts) "
                 "and were dropped.", WARN, "⚠")
        if stats.hosting and run.results and not opts.filters.no_datacenter:
            note(f"{fmt(stats.hosting)} of {fmt(len(run.results))} hits ({pct(stats.hosting, len(run.results))}) "
                 "probably exit from datacenters – those often get blocked sooner. "
                 "Only the others: --no-datacenter", MUTED, "ℹ")
        if stats.blocklisted and run.results and not opts.filters.no_blocklisted:
            share = pct(stats.blocklisted, len(run.results))
            note(f"{fmt(stats.blocklisted)} of {fmt(len(run.results))} hits ({share}) "
                 "exit from an IP on the SpamCop blocklist – sites that use it show captchas or block them. "
                 "Only the others: --no-blocklisted", MUTED, "ℹ")
        if run.reached_goal:
            note(f"Goal of {fmt(opts.want)} hits reached – stopped early.", GOOD, "✔")
        elif run.interrupted:
            note("Interrupted – the hits so far were saved.")
