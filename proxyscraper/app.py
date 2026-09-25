"""Ein kompletter Lauf in klaren Phasen: Netz → Jobs → Prüfen → Lernen & Bericht."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Tuple

from rich.live import Live
from rich.text import Text

from . import sources as srcs
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
from .options import RunOptions
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
    render_summary,
    section,
    section_end,
    widgets,
)
from .ui.serve import ServeDashboard
from .ui.widgets import shown_proxy

OWN_IP_URLS = (
    f"https://{JUDGE_HOST}/",       # HTTPS zuerst: wird nicht von Relays/Firmenproxys umgeleitet
    "https://api.ipify.org/",
    f"http://{JUDGE_HOST}/",        # Port 80 kann über einen anderen Weg (andere IP) laufen
)


async def get_own_ips() -> List[str]:
    """Alle IPs, unter denen du nach außen sichtbar bist – die wichtigste zuerst."""

    async def one(url: str) -> str:
        try:
            ip = (await http_get(url, timeout=6)).strip().decode("ascii", "ignore")
            ipaddress.IPv4Address(ip)
            return ip
        except Exception:  # Dienst nicht erreichbar -> nächste Quelle zählt
            return ""

    ips = await asyncio.gather(*(one(u) for u in OWN_IP_URLS))
    return list(dict.fromkeys(ip for ip in ips if ip))


async def confirm_target() -> Optional[str]:
    """IP des Bestätigungsziels – nur wenn genau diese IP so antwortet, wie die Bestätigung es erwartet."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(CONFIRM_HOST, CONFIRM_PORT, family=socket.AF_INET)
    except OSError:  # nicht auflösbar -> ohne Bestätigung weiter, mit Hinweis
        return None
    ip = infos[0][4][0]
    return ip if await probe_confirm_target(ip, timeout=8) else None


def load_recheck_jobs(target: str, types, history: ProxyHistory) -> List[str]:
    """--recheck: Datei, sonst letzter Lauf plus Verlauf."""
    if target:
        lines = Path(target).expanduser().read_text(encoding="utf-8").splitlines()
        # Zeilen ohne typ:// in Dateien wie http.txt bekommen den Typ aus dem Dateinamen
        default = next((t for t in PROXY_TYPES if t in Path(target).name.lower()), None)
        keys = parse_keys(lines, default)
    else:
        keys = parse_keys(latest_results()) + history.ranked_keys()
        keys = list(dict.fromkeys(keys))
    return [k for k in keys if split_key(k)[0] in types]


def is_network_blocked(stats: LiveStats) -> bool:
    """Kommt (fast) gar nichts durch, blockiert vermutlich eine Firewall Proxy-Verbindungen.

    Fake-Proxys zählen mit: Sie bestehen die Basisprüfung, die Verbindung klappt also – ein Netz
    voller Honeypots ist kein blockiertes Netz, und aus dem Lauf soll trotzdem gelernt werden.
    """
    reached = stats.found + stats.fakes + stats.tampered
    return stats.checked >= 1000 and reached < stats.checked * BLOCKED_HIT_RATE


def next_steps(opts: RunOptions, kept: List[CheckResult]) -> List[Tuple[str, str]]:
    """Fertige Befehle für das, was man nach einem Lauf meistens als Nächstes tut."""
    program = "python3 proxy_scraper.py" if is_checkout() else "proxy-scraper"
    steps: List[Tuple[str, str]] = []
    if kept:
        # HTTPS nur vorschlagen, wenn der Proxy den HTTPS-Test bestanden hat – sonst scheitert der Befehl
        secure = [r for r in kept if r.https]
        pool = secure or kept
        # Proxys ohne Login bevorzugen – der Befehl steht im Terminal, da gehört kein Passwort hin
        best = min([r for r in pool if "@" not in r.proxy] or pool, key=lambda r: r.latency)
        scheme = "socks5h" if best.ptype == "socks5" else best.ptype
        target = "https://api.ipify.org" if best.https else "http://api.ipify.org"
        steps.append(("Schnellsten testen", f"curl -x {scheme}://{shown_proxy(best.proxy)} {target}"))
        if not opts.serve:
            steps.append(("Als Proxy-Server", f"{program} --recheck --serve"))
    steps.append(("Später neu prüfen", f"{program} --recheck"))
    return steps


def pool_recheck(checker: Checker):
    """Nachprüfung für ausgemusterte Proxys des Proxy-Servers: die normale Prüfung, aber am Cache vorbei."""
    async def recheck(result: CheckResult) -> bool:
        # der Checker merkt sich unerreichbare Adressen für den Rest des Laufs – genau das soll hier nochmal
        # versucht werden
        checker.unreachable.discard(parse_endpoint(result.proxy).address)
        return await checker.check(result.key) is not None
    return recheck


class Run:
    def __init__(self, opts: RunOptions, show_banner: bool = True):
        self.opts = opts
        self.show_banner = show_banner
        self.started = time.perf_counter()
        self.quality = srcs.SourceStats()
        self.history = ProxyHistory()
        self.scraped: Optional[ScrapeResult] = None
        self.judges: List[JudgeProbe] = []  # erreichbare Prüfziele, schnellstes zuerst
        self.integrity: Optional[bytes] = None  # Hash der Vergleichsseite (siehe Checker.tampers)
        self.checker: Optional[Checker] = None
        self.confirm_ip: Optional[str] = None
        self.targets: List[Tuple[Target, str]] = []
        self.own_ips: List[str] = []

    async def execute(self) -> int:
        if self.show_banner:
            widgets.console.print(banner())
        section("Vorbereitung")
        try:
            with widgets.console.status("Prüfe Netzwerk …", spinner="dots", spinner_style=ACCENT):
                ready = await self.prepare_network()
            if not ready:
                return 1
            self.show_mode()
            jobs = await self.gather_jobs()
            if not jobs:
                note("Keine Proxys zum Prüfen gefunden.", BAD, "✘")
                return 1
        finally:
            section_end()
        await self.check_and_report(jobs)
        return 0

    # ------------------------------------------------------------------ Phase 0: Netz

    async def prepare_network(self) -> bool:
        self.judges, self.own_ips = await asyncio.gather(rank_judges(), get_own_ips())
        if not self.judges:
            note("Kein Prüfziel erreichbar (checkip.amazonaws.com, ifconfig.me, …) – Internetverbindung prüfen.",
                 BAD, "✘")
            return False
        if not self.own_ips:  # die üblichen Dienste für die eigene IP sind weg – die Prüfziele haben sie gesehen
            # nur IPv4 – der Checker vergleicht mit IPv4-Exit-IPs; eine IPv6 (z. B. iCloud Private Relay) passt
            # nie und würde nur die Warnung "Eigene IP unbekannt" verschlucken
            self.own_ips = list(dict.fromkeys(j.seen_ip for j in self.judges if j.seen_ip and "." in j.seen_ip))
        ips = self.own_ips
        info("Deine IP", Text.assemble(
            (ips[0], "bold") if ips else ("unbekannt", WARN),
            (f"  (auf Port 80 zusätzlich {', '.join(ips[1:])})" if len(ips) > 1 else "", MUTED),
        ))
        if not await self.resolve_targets():
            return False
        self.confirm_ip = await confirm_target()
        if self.confirm_ip:  # Vergleichsseite für die Prüfung auf veränderte Inhalte
            self.integrity = await integrity_reference(timeout=8)
        best, reserve = self.judges[0], [j.judge.host for j in self.judges[1:]]
        info("Prüfziel", Text.assemble(
            (f"{best.judge.host} ({best.ip}, {best.latency} ms)", MUTED),
            (f"  ·  Reserve: {', '.join(reserve)}", MUTED) if reserve else "",
            (f"  ·  Bestätigung über {CONFIRM_HOST}", MUTED) if self.confirm_ip else "",
        ))
        if self.confirm_ip and self.integrity is None:
            note(f"Vergleichsseite von {CONFIRM_HOST} nicht erreichbar – Proxys, die Inhalte verändern, "
                 "werden in diesem Lauf nicht erkannt.")
        if not self.confirm_ip:
            note(f"{CONFIRM_HOST} nicht erreichbar – ohne zweite Bestätigung können Fake-Proxys "
                 "(Honeypots) durchrutschen, und die Anonymität bleibt unbekannt.")
        if not ips:
            note("Eigene IP unbekannt – transparente Proxys (verraten deine IP) werden nicht aussortiert.")
        return True

    async def resolve_targets(self) -> bool:
        """Zielseiten einmal auflösen – SOCKS4 braucht IPs, und ein Tippfehler soll sofort auffallen."""
        loop = asyncio.get_running_loop()
        for url in self.opts.filters.targets:
            target = parse_target(url)
            try:
                infos = await loop.getaddrinfo(target.host, target.port, family=socket.AF_INET)
            except OSError:
                note(f"Zielseite {target.host} lässt sich nicht auflösen – Tippfehler?", BAD, "✘")
                return False
            self.targets.append((target, infos[0][4][0]))
        if self.targets:
            info("Zielseiten", ", ".join(t.label for t, _ in self.targets))
        return True

    def show_mode(self) -> None:
        opts = self.opts
        modes = ["mit HTTPS-Test" if opts.details else "ohne HTTPS-Test (--fast)"]
        modes.append("Länder" if opts.geo else "ohne Länder")
        if opts.filters.active:
            modes.append(f"Filter: {opts.filters.describe()}")
        if opts.want:
            modes.append(f"stoppt bei {fmt(opts.want)} Treffern")
        if opts.check_timeout < opts.timeout:
            modes.append(f"Timeout {opts.check_timeout:g} s dank Latenzlimit".replace(".", ","))
        info("Modus", " · ".join(modes))

    # ------------------------------------------------------------------ Phase 1+2: Jobs

    async def gather_jobs(self) -> List[str]:
        opts = self.opts
        if opts.recheck is not None:
            jobs = load_recheck_jobs(opts.recheck, opts.types, self.history)
            info("Recheck", f"{fmt(len(jobs))} Proxys aus {opts.recheck or 'letztem Lauf + Verlauf'}")
        else:
            jobs = await self._scrape_jobs()

        known = sum(1 for k in jobs if k in self.history) if len(self.history) else 0
        if known:
            info("Verlauf", f"{fmt(known)} früher funktionierende Proxys werden zuerst geprüft")
        if opts.limit:
            jobs = jobs[: opts.limit]
            info("Limit", f"prüfe die {fmt(len(jobs))} vielversprechendsten")
        return jobs

    async def _scrape_jobs(self) -> List[str]:
        plan = await collect_sources(self.opts, self.quality)
        info("Quellen", Text.assemble(
            (fmt(len(plan.sources)), f"bold {ACCENT}"), " aktiv  ",
            (f"({fmt(plan.n_curated)} kuratiert · {fmt(plan.n_meta)} aus {plan.meta_ok}/{plan.meta_total} "
             f"Meta-Listen · {fmt(plan.n_discovered)} entdeckt)", MUTED),
        ))
        if plan.discovery_ran and not plan.discovery_token:
            note("GitHub-Discovery ohne Token nur eingeschränkt – `gh auth login` oder GITHUB_TOKEN setzen.",
                 MUTED, "ℹ")
        if plan.skipped:
            parts = ", ".join(f"{n} {reason}" for reason, n in plan.skipped.most_common())
            info("Übersprungen", Text.assemble(parts, ("  (alle erzwingen: --all-sources)", MUTED)))

        t0 = time.perf_counter()
        view = CollectView(len(plan.sources), self.started)
        with Live(view, console=widgets.console, refresh_per_second=10, transient=True):
            cache = FetchCache(enabled=not self.opts.no_cache)
            self.scraped = await scrape(plan.sources, self.opts.types, self.quality, view, cache)
        self.quality.save()
        cache.save()
        res = self.scraped
        info("Gesammelt", Text.assemble(
            (fmt(len(res.index)), f"bold {GOOD}"), " einzigartige Proxys aus ",
            f"{res.ok_sources}/{len(plan.sources)} Quellen",
            (f"  ({view.bytes / 2**20:.0f} MB in {fmt_duration(time.perf_counter() - t0)}"
             + (f", {view.cached} unverändert aus dem Cache" if view.cached else "") + ")", MUTED),
        ))
        if INSECURE_HOSTS:
            hosts = sorted(INSECURE_HOSTS)
            note(f"Zertifikat nicht prüfbar (TLS-Inspektion im Netz?), trotzdem geladen: "
                 f"{', '.join(hosts[:4])}{' …' if len(hosts) > 4 else ''}", MUTED, "ℹ")
        return prioritize(res, self.quality, self.history, self.opts.types)

    # ------------------------------------------------------------------ Phase 3+4: Prüfen, Lernen, Bericht

    async def check_and_report(self, jobs: List[str]) -> None:
        # Worker + gedeckelte Detailverbindungen + Reserve für Quellen, Geo und Co.
        fd = raise_fd_limit(self.opts.concurrency + DETAIL_CONNECTIONS + 512)
        opts = replace(self.opts, concurrency=min(self.opts.concurrency, max(fd - DETAIL_CONNECTIONS - 256, 64)))

        writer = ResultWriter(extra_file=Path(opts.output) if opts.output else None, exports=opts.exports)
        stats = LiveStats(Counter(split_key(k)[0] for k in jobs))
        dashboard = CheckDashboard(stats, writer.live_path, opts.concurrency, opts.details,
                                   opts.filters.describe(), opts.want, opts.filters.targets)
        judge = self.judges[0]
        checker = Checker(judge.ip, self.own_ips, opts.check_timeout, opts.check_connect_timeout,
                          self.confirm_ip, detail_timeout=opts.timeout,
                          detail_connect_timeout=opts.connect_timeout, targets=self.targets,
                          https_test=not opts.fast or opts.filters.https_only, judge=judge.judge,
                          integrity_reference=self.integrity)
        self.checker = checker  # für den Proxy-Server: Nachprüfen ausgemusterter Proxys
        watch = JudgeWatch(self.judges, lambda new: checker.use_judge(new.judge, new.ip))
        dashboard.judge = judge.judge.host
        # Länder-Datenbank sofort aus data/ (2 ms); ist sie alt oder fehlt, im Hintergrund neu laden –
        # bis dahin übernimmt ip-api.com, niemand wartet auf den Download
        country_db = CountryDB.load() if opts.geo else None
        geo = GeoResolver(enabled=opts.geo, offline=country_db)
        refresh = None
        if opts.geo and not is_current(country_db):
            refresh = asyncio.ensure_future(self.refresh_country_db(geo))
        widgets.console.print()
        run = await run_checks(
            jobs, checker, opts, dashboard, writer, geo,
            live_factory=lambda renderable: Live(renderable, console=widgets.console, refresh_per_second=6),
            watch=watch,
        )

        if refresh and not refresh.done():
            refresh.cancel()  # Download läuft noch – beim nächsten Lauf wieder
        kept = [r for r in run.results if opts.filters.accepts(r)]
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
        """Die gefundenen Proxys als lokalen rotierenden Proxy-Server bereitstellen, bis Strg+C."""
        if not proxies:
            note("Kein passender Proxy gefunden – der Proxy-Server startet nicht.", BAD, "✘")
            return
        pool = ProxyPool(proxies, strategy=self.opts.rotate, sticky_seconds=self.opts.sticky)
        server = RotatingServer(pool, port=self.opts.serve, timeout=self.opts.timeout)
        try:
            await server.start()
        except OSError as e:
            note(f"Port {self.opts.serve} ist nicht verfügbar ({e.strerror or e}) – anderen mit --serve PORT wählen.",
                 BAD, "✘")
            return
        stop = asyncio.Event()
        widgets.console.print()
        fresh = None
        if self.checker:  # ausgemusterte Proxys alle 5 Minuten nachprüfen und bei Erfolg zurückholen
            fresh = asyncio.ensure_future(server.keep_fresh(pool_recheck(self.checker)))
        try:
            with on_interrupt(asyncio.get_running_loop(), stop.set), \
                    Live(ServeDashboard(server), console=widgets.console, refresh_per_second=4):
                await stop.wait()
        finally:
            if fresh:
                fresh.cancel()
            await server.close()
        st = server.stats
        note(f"Proxy-Server beendet – {fmt(st.requests)} Anfragen, {fmt(st.ok)} erfolgreich.", GOOD, "✔")

    @staticmethod
    async def refresh_country_db(geo: GeoResolver) -> None:
        """Neue Länder-Datenbank laden und sofort nutzen – Fehler sind egal, dann bleibt es bei ip-api."""
        try:
            db = await load_country_db()
        except Exception:
            return
        if db is not None:
            geo.use_offline(db)

    def learn(self, run: CheckRun, network_blocked: bool):
        """Quellen-Statistik und Verlauf aktualisieren – bei blockiertem Netz nur die Treffer."""
        per_source = attribute_results(self.scraped, run.checked, run.working) if self.scraped else {}
        if not network_blocked:
            # Bei blockiertem Netz wären alle Quellen und bekannten Proxys zu Unrecht "tot"
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
                f"[bold]{fmt(stats.checked)} Proxys geprüft, nur {fmt(stats.found)} funktionieren.[/] "
                "Dein Netzwerk (Firmen-/Schul-Firewall) blockiert vermutlich Proxy-Verbindungen – probier es "
                f"in einem anderen Netz, z. B. über einen Handy-Hotspot. [{MUTED}]Statistik & Verlauf wurden dafür "
                "nicht abgewertet.[/]"
            )
        if opts.geo and geo.failed:
            if geo.offline:
                note("ip-api.com nicht erreichbar – Adressen, die nicht in der DB-IP-Datenbank stehen, "
                     "bleiben ohne Land.", MUTED, "ℹ")
            else:
                note("Länder-Datenbank und ip-api.com nicht erreichbar – Länder fehlen.", MUTED, "ℹ")
        if opts.filters.countries and not kept and run.results:
            note("Kein Treffer im gewünschten Land – Filter lockern oder länger laufen lassen.", MUTED, "ℹ")
        if run.judge_switches:
            note(f"Prüfziel ausgefallen, gewechselt: {', '.join(run.judge_switches)}. {fmt(run.rechecked)} Proxys "
                 "wurden erneut geprüft und zählen nicht für die Quellen-Statistik.", WARN, "⚠")
        if stats.tampered:
            note(f"{fmt(stats.tampered)} Proxys haben eine Testseite verändert (meist mit eingeschleusten Skripten) "
                 "und wurden aussortiert.", WARN, "⚠")
        if run.reached_goal:
            note(f"Ziel von {fmt(opts.want)} Treffern erreicht – vorzeitig beendet.", GOOD, "✔")
        elif run.interrupted:
            note("Abgebrochen – bisherige Treffer wurden gespeichert.")
