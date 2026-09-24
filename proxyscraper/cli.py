"""Kommandozeile: Argumente einlesen und den passenden Ablauf starten."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from typing import List, Optional

from . import sources as srcs
from .app import Run
from .compat import ensure_utf8_output
from .options import (
    DEFAULT_CONCURRENCY,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_DISCOVER_REPOS,
    DEFAULT_TIMEOUT,
    RunOptions,
)
from .parsing import PROXY_TYPES
from .ui import banner, console, note, render_source_ranking


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
    g.add_argument("-c", "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                   help=f"gleichzeitige Prüfungen (Standard: {DEFAULT_CONCURRENCY})")
    g.add_argument("-t", "--timeout", type=float, default=DEFAULT_TIMEOUT,
                   help=f"Timeout pro Proxy in Sekunden (Standard: {DEFAULT_TIMEOUT:g})")
    g.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT,
                   help=f"max. Zeit für den TCP-Verbindungsaufbau in Sekunden (Standard: {DEFAULT_CONNECT_TIMEOUT:g})")
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
    s.add_argument("--discover-repos", type=int, default=DEFAULT_DISCOVER_REPOS,
                   help=f"max. Repos bei der Discovery (Standard: {DEFAULT_DISCOVER_REPOS}, ohne Token 40)")
    s.add_argument("--all-sources", action="store_true", help="auch tote, veraltete und unerreichbare Quellen laden")
    s.add_argument("--list-sources", nargs="?", const=50, type=int, metavar="N",
                   help="Rangliste der Quellen nach Trefferquote anzeigen (Standard: Top 50) und beenden")
    return p.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_output()
    args = parse_args(argv)
    if args.list_sources is not None:
        return list_sources(args.list_sources)
    try:
        return asyncio.run(Run(RunOptions.from_args(args)).execute())
    except KeyboardInterrupt:
        note("Abgebrochen.")
        return 130


if __name__ == "__main__":
    sys.exit(run())
