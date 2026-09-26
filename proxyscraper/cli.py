"""Command line: read the arguments and start the matching flow."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from typing import List, Optional

from rich.console import Console
from rich.text import Text

from . import __version__
from . import sources as srcs
from .app import Run
from .compat import ensure_utf8_output
from .completion import CompletionAction
from .exporters import EXPORTERS, parse_exports
from .history import ProxyHistory
from .options import (
    DEFAULT_CONCURRENCY,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_DISCOVER_REPOS,
    DEFAULT_SERVE_PORT,
    DEFAULT_TIMEOUT,
    STDOUT,
    RunOptions,
)
from .output import has_latest_results
from .parsing import PROXY_TYPES
from .preferences import load_last_argv, save_last_argv
from .server.pool import STRATEGIES
from .targets import parse_target
from .ui import ACCENT, BAD, MUTED, banner, note, render_source_ranking, widgets
from .ui.keys import is_interactive
from .ui.wizard import run_wizard


def list_sources(limit: int) -> int:
    """Ranking of every known source by learned hit rate."""
    quality = srcs.SourceStats()
    curated, _meta = srcs.load_source_file()
    urls = set(curated) | set(srcs.load_discovered()) | set(quality.records)
    ranking = quality.ranking(urls)
    rows = [(u, r, quality.skip_reason(u) or "active") for u, r in ranking if r.runs][:limit]
    reasons = Counter(quality.skip_reason(u) or "active" for u, _ in ranking)
    widgets.console.print(banner())
    render_source_ranking(rows, len(urls), reasons)
    return 0


def _number(kind, minimum, strict=False, maximum=None):
    """argparse type for numbers with limits – with an understandable error message."""
    def parse(text: str):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
        if value < minimum or (strict and value == minimum):
            raise argparse.ArgumentTypeError(f"must be {'greater than' if strict else 'at least'} {minimum}")
        if maximum is not None and value > maximum:
            raise argparse.ArgumentTypeError(f"must be at most {maximum}")
        return value
    return parse


def target_url(text: str) -> str:
    """argparse type for --target: normalized URL or an understandable error message."""
    try:
        return parse_target(text).url
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def export_list(text: str) -> List[str]:
    """argparse type for --export: "proxychains,clash" or "all"."""
    try:
        return parse_exports(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


positive_int = _number(int, 1)
port_number = _number(int, 1, maximum=65535)
non_negative_int = _number(int, 0)
positive_float = _number(float, 0, strict=True)
non_negative_float = _number(float, 0)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="proxy-scraper",
        description="Fast asynchronous proxy scraper & checker that learns which sources are worth it",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  proxy-scraper                                setup wizard (in a terminal)\n"
            "  proxy-scraper -y                             collect and check everything right away\n"
            "  proxy-scraper --want 50 --https-only         stop after 50 HTTPS-capable proxies\n"
            "  proxy-scraper --country DE,AT,CH -l 20000    DACH only, the 20,000 best candidates\n"
            "  proxy-scraper --types socks5 --anonymity elite --max-latency 1500\n"
            "  proxy-scraper --target google.com --target discord.com --want 20\n"
            "  proxy-scraper --recheck                      recheck the last hits + history\n"
            "  proxy-scraper --recheck --serve              turn them into a rotating proxy right away\n"
            "  proxy-scraper --list-sources                 source ranking\n"
        ),
    )
    p.add_argument("-V", "--version", action="version", version=f"proxy-scraper {__version__}")
    p.add_argument("--completion", action=CompletionAction, metavar="SHELL",
                   help="print tab completion for bash, zsh or fish, e.g. eval \"$(proxy-scraper "
                        "--completion zsh)\"")
    m = p.add_argument_group("Start")
    m.add_argument("-i", "--interactive", action="store_true",
                   help="setup wizard: pick with the arrow keys what to look for "
                        "(shows up automatically without arguments; other arguments are used as starting values)")
    m.add_argument("-y", "--yes", action="store_true", help="skip the wizard and start right away with the defaults")

    g = p.add_argument_group("Checks")
    g.add_argument("-c", "--concurrency", type=positive_int, default=DEFAULT_CONCURRENCY,
                   help=f"concurrent checks (default: {DEFAULT_CONCURRENCY})")
    g.add_argument("-t", "--timeout", type=positive_float, default=DEFAULT_TIMEOUT,
                   help=f"timeout per proxy in seconds (default: {DEFAULT_TIMEOUT:g})")
    g.add_argument("--connect-timeout", type=positive_float, default=DEFAULT_CONNECT_TIMEOUT,
                   help=f"max. time for the TCP connect in seconds (default: {DEFAULT_CONNECT_TIMEOUT:g})")
    g.add_argument("--types", nargs="+", choices=list(PROXY_TYPES), default=list(PROXY_TYPES),
                   help="which protocols (default: all)")
    g.add_argument("-l", "--limit", type=non_negative_int, default=0,
                   help="only check the N most promising proxies (by history & source quality)")
    g.add_argument("--want", type=non_negative_int, default=0, metavar="N",
                   help="stop as soon as N matching proxies are found")
    g.add_argument("--fast", action="store_true",
                   help="skip the HTTPS test (faster); confirmation and anonymity still run")
    g.add_argument("--no-geo", action="store_true", help="don't look up countries")
    g.add_argument("--no-dnsbl", action="store_true",
                   help="don't look up whether exit IPs are on the SpamCop blocklist")
    g.add_argument("--recheck", nargs="?", const="", metavar="FILE",
                   help="only check proxies from FILE – without FILE: last run + history; "
                        "'live': the live list from GitHub (seconds instead of minutes, e.g. with --serve)")

    f = p.add_argument_group("Filters (for the result files)")
    f.add_argument("--country", metavar="CC", help="only these countries, e.g. DE,AT,CH")
    f.add_argument("--https-only", action="store_true", help="only proxies that can tunnel HTTPS sites")
    f.add_argument("--anonymity", choices=["anonymous", "elite"], help="minimum anonymity")
    f.add_argument("--max-latency", type=non_negative_int, default=0, metavar="MS",
                   help="only proxies up to this latency")
    f.add_argument("--no-datacenter", action="store_true",
                   help="no proxies that exit from datacenters (cloud/hosting) – those often get blocked sooner")
    f.add_argument("--no-blocklisted", action="store_true",
                   help="no proxies whose exit IP is on the SpamCop blocklist – those often get captchas")
    f.add_argument("--target", action="append", type=target_url, metavar="URL",
                   help="only proxies that reach this site (repeatable), e.g. --target google.com")

    v = p.add_argument_group("Proxy server")
    v.add_argument("--serve", nargs="?", const=DEFAULT_SERVE_PORT, default=0, type=port_number, metavar="PORT",
                   help=f"serve the hits as a rotating proxy on 127.0.0.1:PORT after the run "
                        f"(default port: {DEFAULT_SERVE_PORT}); quick to start with --recheck")
    v.add_argument("--rotate", choices=STRATEGIES, default="weighted",
                   help="which proxy comes next: weighted (fast & reliable preferred, default), "
                        "random, round-robin or fastest")
    v.add_argument("--serve-host", default="127.0.0.1", metavar="ADDRESS",
                   help="address of the proxy server (default: 127.0.0.1). 0.0.0.0 makes it reachable from outside – "
                        "only for Docker with -p 127.0.0.1:8899:8899 or behind a firewall")
    v.add_argument("--serve-password", default=os.environ.get("PROXY_SCRAPER_SERVE_PASSWORD", ""), metavar="SECRET",
                   help="clients must send this password in the proxy login (HTTP and SOCKS5); better set "
                        "PROXY_SCRAPER_SERVE_PASSWORD, so it doesn't show up in the process list")
    v.add_argument("--serve-refill", type=non_negative_float, default=0, metavar="HOURS",
                   help="every HOURS check fresh proxies in the background (the live list with --recheck live, "
                        "otherwise the last run + history) and add the hits to the running server")
    v.add_argument("--sticky", type=non_negative_int, default=0, metavar="SEC",
                   help="the same target site keeps the same proxy for this long (e.g. for logins); "
                        "per request this also works with the user name session-NAME")

    o = p.add_argument_group("Output")
    o.add_argument("-o", "--output", metavar="FILE",
                   help="also write all hits as type://ip:port to this file; - prints them to stdout "
                        "(the interface moves to stderr then)")
    o.add_argument("--export", type=export_list, metavar="FORMATS",
                   help=f"extra formats in the results folder: {', '.join(EXPORTERS)} or all "
                        "(e.g. --export proxychains,clash)")

    s = p.add_argument_group("Sources")
    s.add_argument("--discover", action="store_true",
                   help="look for new proxy lists on GitHub now (with a GitHub token this also runs once a day)")
    s.add_argument("--no-discover", action="store_true", help="no automatic GitHub search")
    s.add_argument("--discover-repos", type=non_negative_int, default=DEFAULT_DISCOVER_REPOS,
                   help=f"max. repos during discovery (default: {DEFAULT_DISCOVER_REPOS}, 40 without a token)")
    s.add_argument("--all-sources", action="store_true", help="also load dead, outdated and unreachable sources")
    s.add_argument("--no-cache", action="store_true",
                   help="reload every list completely (otherwise unchanged ones are skipped via ETag)")
    s.add_argument("--list-sources", nargs="?", const=50, type=positive_int, metavar="N",
                   help="show the source ranking by hit rate (default: top 50) and exit")
    return p.parse_args(argv)


def last_options() -> Optional[RunOptions]:
    argv = load_last_argv()
    if argv is None:
        return None
    try:
        return RunOptions.from_args(parse_args(argv))
    except SystemExit:  # the saved choice no longer fits the current options
        return None


def choose_interactively(initial: RunOptions) -> Optional[RunOptions]:
    widgets.console.print(banner())
    can_recheck = has_latest_results() or ProxyHistory.exists()
    opts = run_wizard(initial, last_options(), can_recheck, widgets.console)
    if opts is None:
        return None
    save_last_argv(opts.to_argv())
    widgets.console.print(Text.assemble(
        ("  ▸ ", ACCENT), ("Next time, directly: ", MUTED), (opts.to_command(), "bold"),
    ))
    return opts


def wants_wizard(args: argparse.Namespace, argv: List[str]) -> bool:
    """-i forces the wizard; without arguments it only shows up in a terminal. -y skips it."""
    if args.interactive:
        return True
    return not argv and not args.yes and is_interactive()


def install_uvloop() -> None:
    try:
        import uvloop  # optional (pip install "proxy-scraper[fast]"), makes asyncio even faster
    except ImportError:
        return
    uvloop.install()


def run(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_output()
    install_uvloop()
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    if args.list_sources is not None:
        return list_sources(args.list_sources)
    opts = RunOptions.from_args(args)
    if opts.output == STDOUT:
        widgets.console = Console(highlight=False, stderr=True)  # stdout only carries the hits
    use_wizard = wants_wizard(args, argv)
    if use_wizard:
        if not is_interactive():
            note("The setup wizard (-i) needs a terminal.", BAD, "✘")
            return 2
        opts = choose_interactively(opts)
        if opts is None:
            note("Cancelled – nothing was started.", MUTED, "ℹ")
            return 0
    try:
        # after the wizard the banner is already on screen
        return asyncio.run(Run(opts, show_banner=not use_wizard).execute())
    except KeyboardInterrupt:
        note("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(run())
