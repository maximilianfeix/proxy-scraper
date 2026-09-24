"""Kommandozeile und Gesamtablauf."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import resource
import socket
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List, Optional

from rich.live import Live
from rich.text import Text

from . import sources as srcs
from .checker import JUDGE_HOST, JUDGE_PORT, Checker
from .geo import GeoResolver
from .history import ProxyHistory
from .netio import INSECURE_HOSTS, http_get
from .output import Filters, ResultWriter, latest_results
from .parsing import PROXY_TYPES, parse_keys, split_key
from .pipeline import (
    attribute_results,
    best_sources,
    collect_sources,
    prioritize,
    run_checks,
    scrape,
)
from .ui import (
    ACCENT,
    BLOCKED_HIT_RATE,
    GOOD,
    MUTED,
    CheckDashboard,
    CollectView,
    LiveStats,
    banner,
    console,
    fmt,
    fmt_duration,
    info,
    note,
    render_source_ranking,
    render_summary,
)

def raise_fd_limit(wanted: int) -> int:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
    if soft < target:
        for t in (target, 10240, 4096):
            try:
                resource.setrlimit(resource.RLIMIT_NOFILE, (t, hard))
                return t
            except (ValueError, OSError):
                continue
    return resource.getrlimit(resource.RLIMIT_NOFILE)[0]


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


async def main(args) -> int:
    started = time.perf_counter()
    types = args.types
    fd = raise_fd_limit(args.concurrency + 512)
    concurrency = min(args.concurrency, max(fd - 256, 64))
    filters = Filters(
        countries={c.strip().upper() for c in (args.country or "").split(",") if c.strip()},
        https_only=args.https_only,
        min_anonymity=args.anonymity or "",
        max_latency=args.max_latency,
    )
    details = not args.fast or filters.needs_details
    geo_enabled = not args.no_geo or bool(filters.countries)

    console.print(banner())

    # 0) Netz
    loop = asyncio.get_running_loop()
    try:
        judge_ip = (await loop.getaddrinfo(JUDGE_HOST, JUDGE_PORT, family=socket.AF_INET))[0][4][0]
    except OSError:
        note(f"Kann {JUDGE_HOST} nicht auflösen – Internetverbindung prüfen.", "red", "✘")
        return 1
    own_ips = await get_own_ips()
    info("Deine IP", Text.assemble(
        (own_ips[0], "bold") if own_ips else ("unbekannt", "yellow"),
        (f"  (auf Port 80 zusätzlich {', '.join(own_ips[1:])})" if len(own_ips) > 1 else "", MUTED),
    ))
    info("Prüfziel", f"{JUDGE_HOST} ({judge_ip})", MUTED)
    if not own_ips:
        note("Eigene IP unbekannt – transparente Proxys (verraten deine IP) werden nicht aussortiert.")
    modes = ["HTTPS- & Anonymitätstest" if details else "nur Basistest (--fast)"]
    modes.append("Länder" if geo_enabled else "ohne Länder")
    if filters.active:
        modes.append(f"Filter: {filters.describe()}")
    if args.want:
        modes.append(f"stoppt bei {fmt(args.want)} Treffern")
    info("Modus", " · ".join(modes))

    quality = srcs.SourceStats()
    history = ProxyHistory()
    res = None

    # 1) + 2) Quellen & Sammeln
    if args.recheck is not None:
        jobs = load_recheck_jobs(args.recheck, types, history)
        info("Recheck", f"{fmt(len(jobs))} Proxys aus {args.recheck or 'letztem Lauf + Verlauf'}")
    else:
        plan = await collect_sources(args, quality)
        src_line = Text.assemble(
            (fmt(len(plan.sources)), f"bold {ACCENT}"), " aktiv  ",
            (f"({fmt(plan.n_curated)} kuratiert · {fmt(plan.n_meta)} aus {plan.meta_ok}/{plan.meta_total} "
             f"Meta-Listen · {fmt(plan.n_discovered)} entdeckt)", MUTED),
        )
        info("Quellen", src_line)
        if plan.discovery_ran and not plan.discovery_token:
            note("GitHub-Discovery ohne Token nur eingeschränkt – `gh auth login` oder GITHUB_TOKEN setzen.", MUTED, "ℹ")
        if plan.skipped:
            parts = ", ".join(f"{n} {reason}" for reason, n in plan.skipped.most_common())
            info("Übersprungen", Text.assemble(parts, ("  (alle erzwingen: --all-sources)", MUTED)))

        t0 = time.perf_counter()
        view = CollectView(len(plan.sources), started)
        with Live(view, console=console, refresh_per_second=10, transient=True):
            res = await scrape(plan.sources, types, quality, view)
        quality.save()
        info("Gesammelt", Text.assemble(
            (fmt(len(res.index)), f"bold {GOOD}"), " einzigartige Proxys aus ",
            f"{res.ok_sources}/{len(plan.sources)} Quellen", (f"  ({view.bytes / 2**20:.0f} MB in "
                                                             f"{fmt_duration(time.perf_counter() - t0)})", MUTED),
        ))
        if INSECURE_HOSTS:
            hosts = sorted(INSECURE_HOSTS)
            note(f"Zertifikat nicht prüfbar (TLS-Inspektion im Netz?), trotzdem geladen: "
                 f"{', '.join(hosts[:4])}{' …' if len(hosts) > 4 else ''}", MUTED, "ℹ")
        jobs = prioritize(res, quality, history, types)

    known = sum(1 for k in jobs if k in history) if len(history) else 0
    if known:
        info("Verlauf", f"{fmt(known)} früher funktionierende Proxys werden zuerst geprüft")
    if args.limit:
        jobs = jobs[: args.limit]
        info("Limit", f"prüfe die {fmt(len(jobs))} vielversprechendsten")
    if not jobs:
        note("Keine Proxys zum Prüfen gefunden.", "red", "✘")
        return 1

    # 3) Prüfen
    writer = ResultWriter(extra_file=Path(args.output) if args.output else None)
    stats = LiveStats(Counter(split_key(k)[0] for k in jobs))
    dashboard = CheckDashboard(stats, writer.live_path, concurrency, details, filters.describe(), args.want)
    checker = Checker(judge_ip, own_ips, args.timeout, args.connect_timeout)
    geo = GeoResolver(enabled=geo_enabled)
    console.print()
    run = await run_checks(
        jobs, checker, stats, dashboard, writer, filters, geo, details, args.want, concurrency,
        live_factory=lambda renderable: Live(renderable, console=console, refresh_per_second=6),
    )

    # 4) Speichern & lernen
    kept = [r for r in run.results if filters.accepts(r)]
    files = writer.finalize(kept)
    network_blocked = stats.checked >= 1000 and stats.found < stats.checked * BLOCKED_HIT_RATE
    per_source = attribute_results(res, run.checked, run.working) if res else {}
    if not network_blocked:
        # Bei blockiertem Netz wären alle Quellen und bekannten Proxys zu Unrecht "tot"
        quality.record_checks(per_source)
        for key in run.checked:
            if key not in run.working:
                history.record_fail(key)
    for r in run.results:
        history.record_ok(r.key, r.latency, r.exit_ip, country=r.country, anonymity=r.anonymity, https=r.https)
    history.prune()
    history.save()
    quality.save()
    geo.save()

    render_summary(stats, run.results, kept, best_sources(per_source), files, details, filters.describe())
    if network_blocked:
        note(
            f"[bold]{fmt(stats.checked)} Proxys geprüft, nur {fmt(stats.found)} funktionieren.[/] "
            "Dein Netzwerk (Firmen-/Schul-Firewall) blockiert vermutlich Proxy-Verbindungen – probier es "
            "in einem anderen Netz, z. B. über einen Handy-Hotspot. [grey50]Statistik & Verlauf wurden dafür "
            "nicht abgewertet.[/]"
        )
    if geo_enabled and geo.failed:
        note("Länder-API (ip-api.com) nicht erreichbar – Länder fehlen.", MUTED, "ℹ")
    if filters.countries and not kept and run.results:
        note("Kein Treffer im gewünschten Land – Filter lockern oder länger laufen lassen.", MUTED, "ℹ")
    if run.reached_goal:
        note(f"Ziel von {fmt(args.want)} Treffern erreicht – vorzeitig beendet.", GOOD, "✔")
    elif run.interrupted:
        note("Abgebrochen – bisherige Treffer wurden gespeichert.")
    return 0


def list_sources(limit: int) -> int:
    """Rangliste aller bekannten Quellen nach gelernter Trefferquote."""
    quality = srcs.SourceStats()
    curated, _meta = srcs.load_source_file()
    urls = set(curated) | set(srcs.load_discovered()) | set(quality.records)
    ranking = quality.ranking(urls)
    rows = [(u, r, quality.skip_reason(u) or "aktiv") for u, r in ranking if r.runs][:limit]
    reasons = Counter(quality.skip_reason(u) or "aktiv" for u, _ in ranking)
    console.print(banner())
    render_source_ranking(rows, len(urls), reasons)
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="proxy_scraper.py",
        description="Schneller asynchroner Proxy-Scraper & -Checker mit lernender Quellenauswahl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  proxy_scraper.py                              alles sammeln und prüfen\n"
            "  proxy_scraper.py --want 50 --https-only       stoppt nach 50 HTTPS-fähigen Proxys\n"
            "  proxy_scraper.py --country DE,AT,CH -l 20000  nur DACH, die 20.000 besten Kandidaten\n"
            "  proxy_scraper.py --types socks5 --anonymity elite --max-latency 1500\n"
            "  proxy_scraper.py --recheck                    letzte Treffer + Verlauf neu prüfen\n"
            "  proxy_scraper.py --list-sources               Quellen-Rangliste\n"
        ),
    )
    g = p.add_argument_group("Prüfung")
    g.add_argument("-c", "--concurrency", type=int, default=2000, help="gleichzeitige Prüfungen (Standard: 2000)")
    g.add_argument("-t", "--timeout", type=float, default=8.0, help="Timeout pro Proxy in Sekunden (Standard: 8)")
    g.add_argument("--connect-timeout", type=float, default=4.0,
                   help="max. Zeit für den TCP-Verbindungsaufbau in Sekunden (Standard: 4)")
    g.add_argument("--types", nargs="+", choices=list(PROXY_TYPES), default=list(PROXY_TYPES),
                   help="welche Protokolle (Standard: alle)")
    g.add_argument("-l", "--limit", type=int, default=0,
                   help="nur die N vielversprechendsten Proxys prüfen (nach Verlauf & Quellenqualität)")
    g.add_argument("--want", type=int, default=0, metavar="N", help="beenden, sobald N passende Proxys gefunden sind")
    g.add_argument("--fast", action="store_true", help="ohne HTTPS- und Anonymitätstest (schneller)")
    g.add_argument("--no-geo", action="store_true", help="keine Länder ermitteln")
    g.add_argument("--recheck", nargs="?", const="", metavar="DATEI",
                   help="nur Proxys aus DATEI prüfen – ohne DATEI: letzter Lauf + Verlauf")

    f = p.add_argument_group("Filter (für die Ergebnisdateien)")
    f.add_argument("--country", metavar="CC", help="nur diese Länder, z. B. DE,AT,CH")
    f.add_argument("--https-only", action="store_true", help="nur Proxys, die HTTPS-Seiten tunneln können")
    f.add_argument("--anonymity", choices=["anonymous", "elite"], help="Mindest-Anonymität")
    f.add_argument("--max-latency", type=int, default=0, metavar="MS", help="nur Proxys bis zu dieser Latenz")

    o = p.add_argument_group("Ausgabe")
    o.add_argument("-o", "--output", help="zusätzlich alle Treffer als typ://ip:port in diese Datei")

    s = p.add_argument_group("Quellen")
    s.add_argument("--discover", action="store_true",
                   help="jetzt neue Proxy-Listen auf GitHub suchen (mit GitHub-Token sonst automatisch alle 3 Tage)")
    s.add_argument("--no-discover", action="store_true", help="keine automatische GitHub-Suche")
    s.add_argument("--discover-repos", type=int, default=400,
                   help="max. Repos bei der Discovery (Standard: 400, ohne Token 40)")
    s.add_argument("--all-sources", action="store_true", help="auch tote, veraltete und unerreichbare Quellen laden")
    s.add_argument("--list-sources", nargs="?", const=50, type=int, metavar="N",
                   help="Rangliste der Quellen nach Trefferquote anzeigen (Standard: Top 50) und beenden")
    return p.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.list_sources is not None:
        return list_sources(args.list_sources)
    try:
        return asyncio.run(main(args))
    except KeyboardInterrupt:
        note("Abgebrochen.")
        return 130


if __name__ == "__main__":
    sys.exit(run())
