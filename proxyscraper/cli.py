"""Kommandozeile: Argumente einlesen und den passenden Ablauf starten."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from typing import List, Optional

from rich.text import Text

from . import sources as srcs
from .app import Run
from .compat import ensure_utf8_output
from .history import ProxyHistory
from .options import (
    DEFAULT_CONCURRENCY,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_DISCOVER_REPOS,
    DEFAULT_TIMEOUT,
    RunOptions,
)
from .output import has_latest_results
from .parsing import PROXY_TYPES
from .preferences import load_last_argv, save_last_argv
from .ui import ACCENT, MUTED, banner, note, render_source_ranking, widgets
from .ui.keys import is_interactive
from .ui.wizard import run_wizard


def list_sources(limit: int) -> int:
    """Rangliste aller bekannten Quellen nach gelernter Trefferquote."""
    quality = srcs.SourceStats()
    curated, _meta = srcs.load_source_file()
    urls = set(curated) | set(srcs.load_discovered()) | set(quality.records)
    ranking = quality.ranking(urls)
    rows = [(u, r, quality.skip_reason(u) or "aktiv") for u, r in ranking if r.runs][:limit]
    reasons = Counter(quality.skip_reason(u) or "aktiv" for u, _ in ranking)
    widgets.console.print(banner())
    render_source_ranking(rows, len(urls), reasons)
    return 0


def _number(kind, minimum, strict=False):
    """argparse-Typ für Zahlen mit Untergrenze – mit verständlicher Fehlermeldung."""
    def parse(text: str):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"keine Zahl: {text!r}") from None
        if value < minimum or (strict and value == minimum):
            raise argparse.ArgumentTypeError(f"muss {'größer als' if strict else 'mindestens'} {minimum} sein")
        return value
    return parse


positive_int = _number(int, 1)
non_negative_int = _number(int, 0)
positive_float = _number(float, 0, strict=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="proxy_scraper.py",
        description="Schneller asynchroner Proxy-Scraper & -Checker mit lernender Quellenauswahl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  proxy_scraper.py                              Einrichtungsassistent (im Terminal)\n"
            "  proxy_scraper.py -y                           sofort alles sammeln und prüfen\n"
            "  proxy_scraper.py --want 50 --https-only       stoppt nach 50 HTTPS-fähigen Proxys\n"
            "  proxy_scraper.py --country DE,AT,CH -l 20000  nur DACH, die 20.000 besten Kandidaten\n"
            "  proxy_scraper.py --types socks5 --anonymity elite --max-latency 1500\n"
            "  proxy_scraper.py --recheck                    letzte Treffer + Verlauf neu prüfen\n"
            "  proxy_scraper.py --list-sources               Quellen-Rangliste\n"
        ),
    )
    m = p.add_argument_group("Start")
    m.add_argument("-i", "--interactive", action="store_true",
                   help="Einrichtungsassistent: per Pfeiltasten auswählen, was gesucht wird "
                        "(kommt ohne Argumente automatisch; übrige Argumente dienen als Startwerte)")
    m.add_argument("-y", "--yes", action="store_true", help="ohne Assistent sofort mit den Standardwerten starten")

    g = p.add_argument_group("Prüfung")
    g.add_argument("-c", "--concurrency", type=positive_int, default=DEFAULT_CONCURRENCY,
                   help=f"gleichzeitige Prüfungen (Standard: {DEFAULT_CONCURRENCY})")
    g.add_argument("-t", "--timeout", type=positive_float, default=DEFAULT_TIMEOUT,
                   help=f"Timeout pro Proxy in Sekunden (Standard: {DEFAULT_TIMEOUT:g})")
    g.add_argument("--connect-timeout", type=positive_float, default=DEFAULT_CONNECT_TIMEOUT,
                   help=f"max. Zeit für den TCP-Verbindungsaufbau in Sekunden (Standard: {DEFAULT_CONNECT_TIMEOUT:g})")
    g.add_argument("--types", nargs="+", choices=list(PROXY_TYPES), default=list(PROXY_TYPES),
                   help="welche Protokolle (Standard: alle)")
    g.add_argument("-l", "--limit", type=non_negative_int, default=0,
                   help="nur die N vielversprechendsten Proxys prüfen (nach Verlauf & Quellenqualität)")
    g.add_argument("--want", type=non_negative_int, default=0, metavar="N",
                   help="beenden, sobald N passende Proxys gefunden sind")
    g.add_argument("--fast", action="store_true",
                   help="ohne HTTPS-Test (schneller); Bestätigung und Anonymität laufen trotzdem")
    g.add_argument("--no-geo", action="store_true", help="keine Länder ermitteln")
    g.add_argument("--recheck", nargs="?", const="", metavar="DATEI",
                   help="nur Proxys aus DATEI prüfen – ohne DATEI: letzter Lauf + Verlauf")

    f = p.add_argument_group("Filter (für die Ergebnisdateien)")
    f.add_argument("--country", metavar="CC", help="nur diese Länder, z. B. DE,AT,CH")
    f.add_argument("--https-only", action="store_true", help="nur Proxys, die HTTPS-Seiten tunneln können")
    f.add_argument("--anonymity", choices=["anonymous", "elite"], help="Mindest-Anonymität")
    f.add_argument("--max-latency", type=non_negative_int, default=0, metavar="MS",
                   help="nur Proxys bis zu dieser Latenz")

    o = p.add_argument_group("Ausgabe")
    o.add_argument("-o", "--output", help="zusätzlich alle Treffer als typ://ip:port in diese Datei")

    s = p.add_argument_group("Quellen")
    s.add_argument("--discover", action="store_true",
                   help="jetzt neue Proxy-Listen auf GitHub suchen (mit GitHub-Token sonst automatisch alle 3 Tage)")
    s.add_argument("--no-discover", action="store_true", help="keine automatische GitHub-Suche")
    s.add_argument("--discover-repos", type=non_negative_int, default=DEFAULT_DISCOVER_REPOS,
                   help=f"max. Repos bei der Discovery (Standard: {DEFAULT_DISCOVER_REPOS}, ohne Token 40)")
    s.add_argument("--all-sources", action="store_true", help="auch tote, veraltete und unerreichbare Quellen laden")
    s.add_argument("--list-sources", nargs="?", const=50, type=positive_int, metavar="N",
                   help="Rangliste der Quellen nach Trefferquote anzeigen (Standard: Top 50) und beenden")
    return p.parse_args(argv)


def last_options() -> Optional[RunOptions]:
    argv = load_last_argv()
    if argv is None:
        return None
    try:
        return RunOptions.from_args(parse_args(argv))
    except SystemExit:  # gespeicherte Auswahl passt nicht mehr zu den aktuellen Optionen
        return None


def choose_interactively(initial: RunOptions) -> Optional[RunOptions]:
    widgets.console.print(banner())
    can_recheck = has_latest_results() or ProxyHistory.exists()
    opts = run_wizard(initial, last_options(), can_recheck, widgets.console)
    if opts is None:
        return None
    save_last_argv(opts.to_argv())
    widgets.console.print(Text.assemble(
        ("  ▸ ", ACCENT), ("Nächstes Mal direkt: ", MUTED), (opts.to_command(), "bold"),
    ))
    return opts


def wants_wizard(args: argparse.Namespace, argv: List[str]) -> bool:
    """-i erzwingt den Assistenten; ohne Argumente kommt er nur im Terminal. -y überspringt ihn."""
    if args.interactive:
        return True
    return not argv and not args.yes and is_interactive()


def run(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_output()
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    if args.list_sources is not None:
        return list_sources(args.list_sources)
    opts = RunOptions.from_args(args)
    use_wizard = wants_wizard(args, argv)
    if use_wizard:
        if not is_interactive():
            note("Der Einrichtungsassistent (-i) braucht ein Terminal.", "red", "✘")
            return 2
        opts = choose_interactively(opts)
        if opts is None:
            note("Abgebrochen – es wurde nichts gestartet.", MUTED, "ℹ")
            return 0
    try:
        # Nach dem Assistenten steht das Banner schon da
        return asyncio.run(Run(opts, show_banner=not use_wizard).execute())
    except KeyboardInterrupt:
        note("Abgebrochen.")
        return 130


if __name__ == "__main__":
    sys.exit(run())
