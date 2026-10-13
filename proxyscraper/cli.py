"""Command line: read the arguments and start the matching flow."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from rich.console import Console
from rich.text import Text

from . import __version__
from . import sources as srcs
from .app import Run, open_server_refusal
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
from .sites import SITES
from .targets import parse_target
from .ui import ACCENT, BAD, GOOD, MUTED, WARN, banner, note, render_source_ranking, widgets
from .ui.keys import is_interactive
from .ui.wizard import run_wizard


def list_sources(limit: int, as_json: bool = False) -> int:
    """Ranking of every known source by learned hit rate – as a table, or as JSON on stdout for scripts."""
    quality = srcs.SourceStats()
    curated, _meta = srcs.load_source_file()
    urls = set(curated) | set(srcs.load_discovered()) | set(quality.records)
    ranking = quality.ranking(urls)
    rows = [(u, r, quality.skip_reason(u) or "active") for u, r in ranking if r.runs][:limit]
    if as_json:
        def stamp(t: float) -> Optional[str]:
            return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") if t else None
        sys.stdout.write(json.dumps([
            {"url": u, "status": status, "hit_rate": round(r.score, 4), "checked": round(r.checked),
             "working": round(r.working), "proxies": r.count, "runs": r.runs,
             "first_seen": stamp(r.first_seen), "last_change": stamp(r.last_change)}
            for u, r, status in rows], indent=1) + "\n")
        return 0
    reasons = Counter(quality.skip_reason(u) or "active" for u, _ in ranking)
    widgets.console.print(banner())
    render_source_ranking(rows, len(urls), reasons)
    return 0


def _say(message: str) -> None:
    """Diagnostics for --pick and --diagnose: stderr, so stdout stays what was asked for."""
    print(f"proxy-scraper: {message}", file=sys.stderr)


def pick(args) -> int:
    """--pick: proxies from the hourly list, nothing but their URLs on stdout (for $(…) in a shell).

    With --verify each candidate is checked from this machine first, and only the ones that pass are printed.
    With --json stdout is one JSON document instead: when the list was published, and per proxy when and how it
    was checked. Exit codes: 0 as many as asked for, 1 none (or nothing could be loaded), 3 with --verify: some,
    but fewer than asked for (they are printed), 130 interrupted."""
    from . import verify
    from .agent import describe
    from .api import _live_selection

    try:
        found, live = asyncio.run(_live_selection(
            types=args.types, countries=args.country or "", https=args.https_only, anonymity=args.anonymity or "",
            max_latency=args.max_latency, no_datacenter=args.no_datacenter, no_blocklisted=args.no_blocklisted,
            min_uptime=args.min_uptime, works_on=args.works_on, min_speed=args.min_speed))
    except (ConnectionError, ValueError) as e:
        _say(str(e))
        return 1
    age = live.age_minutes()
    late = verify.stale_minutes(age, live.run_hours)
    listed = {"updated": live.updated or None, "age_minutes": age, "stale": live.stale()}
    if live.stale():
        _say(f"the published list is {age} minutes old" + (f" ({late} minutes overdue)" if late else "")
             + " – the hourly run seems to have missed. Its proxies were last checked back then"
             + ("" if args.verify else "; add --verify to check them now from this machine"))
    if not found:
        _say("no proxy in the live list matches these filters right now – loosen them, or run a scan of your own")
        return 1
    if not args.verify:
        chosen = found[:args.pick]
        if args.json:
            # checked from GitHub's servers when the list was published – nothing was checked just now
            _print_json({"list": listed, "verified": False,
                         "proxies": [describe(_as_row(p), live.run_hours) for p in chosen]})
        else:
            sys.stdout.write("".join(f"{p.url}\n" for p in chosen))
        return 0

    async def verified():
        checker = await verify.prepare(args.timeout, args.connect_timeout)
        for text in verify.setup_notes(checker):
            _say(text)

        def progress(report) -> None:
            _say(f"{verify.shown(report.ptype, report.proxy)}: {report.verdict()}")

        return checker, await verify.pick_verified(checker, [p.key for p in found], args.pick,
                                                   https=args.https_only, on_report=progress)

    took = verify.timed()
    try:
        checker, selection = asyncio.run(verified())
    except verify.VerifyError as e:
        _say(str(e))
        return 1
    except KeyboardInterrupt:
        _say("interrupted – nothing was printed")
        return verify.EXIT_INTERRUPTED
    reports = selection.verified
    if len(reports) < args.pick:
        _say(verify.shortfall_message(selection, args.pick, args.https_only, checker))
    if args.json:
        _print_json({"list": listed, "verified": True, "verified_from": "this machine", "wanted": args.pick,
                     "tried": selection.tried, "candidates": selection.candidates, "took_seconds": took(),
                     "budget_exhausted": selection.exhausted and len(reports) < args.pick,
                     "proxies": [r.as_dict() for r in reports]})
    else:
        sys.stdout.write("".join(f"{r.url}\n" for r in reports))
    if not reports:
        return 1
    return 0 if len(reports) >= args.pick else verify.EXIT_PARTIAL


def _as_row(p) -> dict:
    """A LiveProxy the way the list had it, for describe()."""
    return {"ptype": p.ptype, "proxy": p.proxy, "country": p.country, "latency": p.latency, "https": p.https,
            "anonymity": p.anonymity, "org": p.org, "hosting": p.hosting, "blocklisted": p.blocklisted,
            "uptime_7d": p.uptime_7d, "sites": p.sites, "speed_kbps": p.speed_kbps, "checked_at": p.checked_at,
            "checks": {name: check.as_dict() for name, check in p.checks.items()}}


def _print_json(data) -> None:
    sys.stdout.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def diagnose(args) -> int:
    """--diagnose PROXY: one proxy, every check, what each one found – as text, or as JSON with --json.

    Exit codes: 0 reached and nothing failed, 1 a check failed, 3 nothing failed but not everything could be
    checked (a check target was down), 2 not a proxy, 130 interrupted."""
    from . import verify

    try:
        key = verify.parse_proxy(args.diagnose)
    except ValueError as e:
        _say(str(e))
        return verify.EXIT_USAGE

    async def run_it():
        checker = await verify.prepare(args.timeout, args.connect_timeout)
        if args.fast:
            checker.https_test = False
        return checker, await verify.examine(checker, key)

    try:
        checker, report = asyncio.run(run_it())
    except verify.VerifyError as e:
        _say(str(e))
        return 1
    except KeyboardInterrupt:
        _say("interrupted")
        return verify.EXIT_INTERRUPTED
    notes = verify.setup_notes(checker)
    if args.json:
        _print_json({**report.as_dict(), "notes": notes})
        return report.exit_code()
    styles = {"passed": GOOD, "failed": BAD, "unavailable": WARN, "skipped": MUTED}
    out = Console(highlight=False, soft_wrap=True)  # the report is what was asked for: stdout, lines unbroken
    for line, state in verify.render(report, notes):
        out.print(Text(line, style=styles.get(state, "")))
    return report.exit_code()


def site_list(text: str) -> List[str]:
    """argparse type for --works-on: google,reddit -> ["google", "reddit"]"""
    names = [n.strip().lower() for n in text.split(",") if n.strip()]
    known = [s.name for s in SITES]
    for n in names:
        if n not in known:
            raise argparse.ArgumentTypeError(f"unknown site {n!r}, use {', '.join(known)}")
    return names


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
percent = _number(int, 0, maximum=100)
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
    p.add_argument("--mcp", action="store_true",
                   help="run as an MCP server over stdio, for AI agents like Claude Code (same as proxy-scraper-mcp; "
                        'needs pip install "proxy-scraper-cli[mcp]")')
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
                   help="only check proxies from FILE, a URL ('https://…/proxies.txt') or stdin ('-') – without FILE: "
                        "last run + history; 'live': the live list from GitHub (seconds instead of minutes, "
                        "e.g. with --serve)")

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

    live = p.add_argument_group("Live list (no scan)")
    live.add_argument("--pick", nargs="?", const=1, type=positive_int, metavar="N",
                      help="print N proxies (default 1) from the hourly checked list that match the filters above, "
                           "one URL per line, and exit – e.g. curl -x \"$(proxy-scraper --pick --https-only)\" …")
    live.add_argument("--verify", action="store_true",
                      help="with --pick: check the candidates from this machine first and print only those that pass "
                           "the handshake, the second request and the content check right now (with --https-only "
                           "also HTTPS). Tries a limited number, a few at a time; exit code 3 if fewer than N passed")
    live.add_argument("--diagnose", metavar="PROXY",
                      help="check one proxy (socks5://host:port, http://user:pass@host:port, host:port) and show "
                           "what each check found: reachable, exit IP, second request, content, HTTPS, latency, "
                           "time – and what could not be checked. --json for a machine-readable report")
    live.add_argument("--min-uptime", type=percent, default=0, metavar="PERCENT",
                      help="with --pick: only proxies on the list in at least this share of the week's checks")
    live.add_argument("--min-speed", type=positive_int, default=0, metavar="KBPS",
                      help="with --pick: only proxies that downloaded at least this many KB/s in the last check")
    live.add_argument("--works-on", type=site_list, default=[], metavar="SITES",
                      help=f"with --pick: only proxies that got through to these sites in the last check "
                           f"({', '.join(s.name for s in SITES)})")

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
    v.add_argument("--serve-open", action="store_true",
                   help="allow --serve-host on an address other than 127.0.0.1 without a password – an open proxy "
                        "for anyone who reaches the port. Only behind a firewall or with docker -p 127.0.0.1:…")
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
                        "(e.g. --export proxychains,singbox)")

    s = p.add_argument_group("Sources")
    s.add_argument("--discover", action="store_true",
                   help="look for new proxy lists on GitHub now (with a GitHub token this also runs once a day)")
    s.add_argument("--no-discover", action="store_true", help="no automatic GitHub search")
    s.add_argument("--discover-repos", type=non_negative_int, default=DEFAULT_DISCOVER_REPOS,
                   help=f"max. repos during discovery (default: {DEFAULT_DISCOVER_REPOS}, 40 without a token)")
    s.add_argument("--all-sources", action="store_true", help="also load dead, outdated and unreachable sources")
    s.add_argument("--source", action="append", metavar="URL|FILE",
                   help="also load this proxy list (repeatable): a URL or a local file, one proxy per line or "
                        "any text with ip:port in it; TYPE=… fixes the type, e.g. socks5=https://…/list.txt – "
                        "without it, lines with a scheme keep theirs and bare ones are tried as HTTP and SOCKS5")
    s.add_argument("--only-sources", action="store_true",
                   help="only the lists given with --source – no built-in, meta or discovered sources")
    s.add_argument("--no-cache", action="store_true",
                   help="reload every list completely (otherwise unchanged ones are skipped via ETag)")
    s.add_argument("--list-sources", nargs="?", const=50, type=positive_int, metavar="N",
                   help="show the source ranking by hit rate (default: top 50) and exit")
    s.add_argument("--json", action="store_true",
                   help="with --list-sources, --pick or --diagnose: print the result as JSON to stdout")
    args = p.parse_args(argv)
    if args.json and args.list_sources is None and args.pick is None and args.diagnose is None:
        p.error("--json only works together with --list-sources, --pick or --diagnose")
    if args.verify and args.pick is None:
        p.error("--verify only works together with --pick")
    if args.diagnose is not None and args.pick is not None:
        p.error("--diagnose checks the one proxy given, --pick takes proxies from the live list – use one of them")
    if (args.min_uptime or args.works_on or args.min_speed) and args.pick is None:
        p.error("--min-uptime, --min-speed and --works-on only work together with --pick")
    if args.pick is not None:  # --pick exits right away: options for a scan or the server would be silently ignored
        scan_only = [flag for dest, flag in (("target", "--target"), ("serve", "--serve"), ("recheck", "--recheck"),
                                             ("want", "--want"), ("output", "-o/--output"), ("export", "--export"))
                     if getattr(args, dest) != p.get_default(dest)]
        if scan_only:
            p.error(f"--pick takes proxies from the live list and exits – {', '.join(scan_only)} belong to a scan")
    return args


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
        import uvloop  # optional (pip install "proxy-scraper-cli[fast]"), makes asyncio even faster
    except ImportError:
        return
    uvloop.install()


def run(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_output()
    install_uvloop()
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    if args.mcp:  # before anything prints: stdout belongs to the MCP protocol from here on
        from .mcp_entry import main as mcp_main
        return mcp_main()
    if args.list_sources is not None:
        return list_sources(args.list_sources, args.json)
    if args.pick is not None:
        return pick(args)
    if args.diagnose is not None:
        return diagnose(args)
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
    refusal = open_server_refusal(opts)
    if refusal:  # before the scan, not after minutes of checking
        note(refusal, BAD, "✘")
        return 2
    try:
        # after the wizard the banner is already on screen
        return asyncio.run(Run(opts, show_banner=not use_wizard).execute())
    except KeyboardInterrupt:
        note("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(run())
