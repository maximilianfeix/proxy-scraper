"""Checking a handful of given proxies from this machine, with every check's outcome kept:

    proxy-scraper --pick 3 --verify      proxies from the hourly list that pass right now, from here
    proxy-scraper --diagnose PROXY       one proxy, check by check

The same checks as a scan (checker.py), but for a few proxies instead of thousands: a fixed number of attempts,
a few at a time, a time limit over all of it. What comes out is what was measured at that moment from this
network against these targets – not a promise that a proxy keeps working, or works for any other site.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

from .checker import Checker, CheckResult, direct_controls, integrity_reference
from .checkstate import (
    BASIC,
    CHECKS,
    CONFIRM,
    CONTENT,
    FAILED,
    HTTPS,
    PASSED,
    REASONS,
    SKIPPED,
    UNAVAILABLE,
    Check,
    now_iso,
)
from .handshake import format_auth
from .judges import probe_judge, rank_judges
from .parsing import TYPE_ALIASES, make_key, split_key

MAX_CONCURRENCY = 8        # proxies examined at once, at most (twice the number asked for, if that is less)
ATTEMPTS_PER_WANTED = 5    # candidates tried per proxy asked for …
MIN_ATTEMPTS, MAX_ATTEMPTS = 10, 60  # … within these bounds
BUDGET_SECONDS = 90.0      # and all of it ends after this long, whatever is still running
STALE_GRACE_MINUTES = 30   # a list older than its interval plus this missed at least one run

EXIT_OK, EXIT_NONE, EXIT_USAGE, EXIT_PARTIAL, EXIT_INTERRUPTED = 0, 1, 2, 3, 130


class VerifyError(Exception):
    """Nothing can be checked right now – the message says why."""


async def prepare(timeout: float, connect_timeout: float) -> Checker:
    """A checker set up like a scan's: the best reachable check target, this machine's own IPs, the confirmation
    target and the reference page – each asked directly once."""
    from .app import confirm_target, get_own_ips  # only here: app pulls in the whole UI

    judges, own_ips = await asyncio.gather(rank_judges(), get_own_ips())
    if not judges:
        raise VerifyError("no check target is reachable (checkip.amazonaws.com, ifconfig.me, …) – "
                          "check your internet connection")
    if not own_ips:
        own_ips = list(dict.fromkeys(j.seen_ip for j in judges if j.seen_ip and "." in j.seen_ip))
    confirm_ip = await confirm_target()
    reference = await integrity_reference(timeout=8) if confirm_ip else None
    best = judges[0]
    checker = Checker(best.ip, own_ips, timeout, connect_timeout, confirm_ip, judge=best.judge,
                      integrity_reference=reference)
    checker.controls = direct_controls(checker, confirm_ip)
    # a scan watches its first check target and switches when it goes down; here there is no watcher, so a
    # failed first request asks the target directly, like the later checks do
    checker.controls[BASIC] = lambda: probe_judge(checker.judge)
    return checker


def setup_notes(checker: Checker) -> List[str]:
    """What this machine could not set up – every check it affects will say "unavailable"."""
    notes = []
    if not checker.confirms:
        notes.append(f"{checker.confirm_host} did not answer directly: no second request and no content check ran")
    elif checker.integrity_reference is None:
        notes.append(f"the reference page from {checker.confirm_host} could not be loaded: no content check ran")
    if not checker.own_ips:
        notes.append("this machine's own IP is unknown: a proxy that passes it on would not be noticed")
    return notes


def parse_proxy(text: str) -> str:
    """'socks5://user:pass@host:1080', 'http://1.2.3.4:8080' or a bare '1.2.3.4:8080' (HTTP) -> key.

    Unlike the lists of a scan, any address is taken: your own proxy on localhost or in a private network is
    exactly what one wants to diagnose."""
    text = text.strip()
    parts = urlsplit(text if "://" in text else f"http://{text}")
    ptype = TYPE_ALIASES.get(parts.scheme.lower())
    try:
        host, port = parts.hostname, parts.port
    except ValueError:
        host = port = None
    if ptype in (None, "auto") or not host or not port or parts.path.strip("/") or parts.query:
        raise ValueError(f"not a proxy: {redacted(text)!r} – give it as socks5://host:port, "
                         "http://user:pass@host:port or host:port (a password with / # ? or @ in it has to be "
                         "percent-encoded)")
    auth = format_auth(unquote(parts.username or ""), unquote(parts.password or ""))
    return make_key(ptype, f"{auth}@{host}:{port}" if auth else f"{host}:{port}")


def redacted(text: str) -> str:
    """What was typed, for an error message: everything between the scheme and the last '@' is a login and
    never shown, however broken the rest is."""
    scheme, sep, rest = text.partition("://")
    prefix, rest = (scheme + sep, rest) if sep else ("", text)
    _login, at, address = rest.rpartition("@")
    if at:
        return f"{prefix}***@{address}"
    parts = rest.split(":")
    if len(parts) > 2:  # host:port:user:pass, the way some lists export logins – or anything else with more colons
        return f"{prefix}{':'.join(parts[:2])}:***"
    return text


def shown(ptype: str, proxy: str) -> str:
    """The proxy for output anyone may read: a password never appears, in text or in JSON."""
    auth, sep, address = proxy.rpartition("@")
    if not sep:
        return f"{ptype}://{proxy}"
    user = "".join(c if c.isprintable() else "?" for c in unquote(auth.partition(":")[0]))
    return f"{ptype}://{user}:***@{address}"


@dataclass
class Report:
    """One proxy, every check – also the ones that never ran, with the reason why not."""
    key: str
    checks: Dict[str, Check] = field(default_factory=dict)
    result: Optional[CheckResult] = None

    @property
    def ptype(self) -> str:
        return split_key(self.key)[0]

    @property
    def proxy(self) -> str:
        return split_key(self.key)[1]

    @property
    def url(self) -> str:
        return f"{self.ptype}://{self.proxy}"

    def state(self, name: str) -> str:
        return self.checks[name].state

    def passes(self, https: bool = False) -> bool:
        """Verified means: reached, confirmed by the second request, content unchanged – all three measured,
        none assumed. With https, the HTTPS test as well."""
        needed = (BASIC, CONFIRM, CONTENT, HTTPS) if https else (BASIC, CONFIRM, CONTENT)
        return all(self.state(name) == PASSED for name in needed)

    def verdict(self) -> str:
        basic = self.checks[BASIC]
        if basic.state == UNAVAILABLE:
            return "could not be checked from this machine"
        if basic.state == FAILED:
            return "not usable from this machine right now"
        failed = [name for name in (CONFIRM, CONTENT) if self.state(name) == FAILED]
        if failed:
            return f"answers, but failed the {' and the '.join(LABELS[name].lower() for name in failed)} check"
        open_ = [name for name in (CONFIRM, CONTENT) if self.state(name) != PASSED]
        https = self.state(HTTPS)
        tail = {PASSED: "", FAILED: "; HTTPS through it did not work", UNAVAILABLE: "; HTTPS could not be tested",
                SKIPPED: "; HTTPS was not tested"}[https]
        if open_:
            return ("reachable, but not verified: "
                    + " and ".join(f"the {LABELS[name].lower()} check gave no result ({self.checks[name].reason})"
                                   for name in open_) + tail)
        return ("passed every check" if https == PASSED else "works for plain HTTP") + tail

    def exit_code(self) -> int:
        """0: reached and nothing failed or left open. 1: a check failed. 3: nothing failed, but not everything
        could be checked."""
        states = [self.state(name) for name in CHECKS]
        if FAILED in states:
            return EXIT_NONE
        return EXIT_PARTIAL if UNAVAILABLE in states else EXIT_OK

    def as_dict(self) -> dict:
        r = self.result
        return {
            "url": shown(self.ptype, self.proxy),
            "protocol": self.ptype,
            "verdict": self.verdict(),
            "exit_ip": r.exit_ip if r else None,
            "anonymity": (r.anonymity or None) if r else None,
            "latency_ms": r.latency if r else None,
            "https": r.https if r else None,
            "checked_at": self.checks[BASIC].at,
            "checks": {name: self.checks[name].as_dict() for name in CHECKS},
        }


LABELS = {BASIC: "Reach", CONFIRM: "Second request", CONTENT: "Content", HTTPS: "HTTPS"}


async def examine(checker: Checker, key: str) -> Report:
    """Every check for one proxy. Unlike a scan this doesn't stop at the first failed check after the basic
    one: for a diagnosis the rest is worth knowing too (three more requests at most)."""
    result, basic = await checker.check_detailed(key)
    report = Report(key, {BASIC: basic}, result)
    if result is not None:
        await checker.confirm(result)
        await checker.tampers(result)
        await checker.enrich(result)
        report.checks.update(result.checks)
    for name in CHECKS:  # whatever never ran says so
        report.checks.setdefault(name, Check(SKIPPED, "earlier_check_failed", at=now_iso()))
    return report


def attempts_for(want: int, candidates: int) -> int:
    return min(candidates, max(MIN_ATTEMPTS, min(MAX_ATTEMPTS, want * ATTEMPTS_PER_WANTED)))


@dataclass
class Selection:
    verified: List[Report]
    tried: int          # candidates that got a verdict
    candidates: int     # how many the list offered
    attempts: int       # how many of them this call was allowed to try
    out_of_time: bool = False

    @property
    def exhausted(self) -> bool:
        """Stopped by a limit of this call (time, or attempts while the list still had more) – not because
        enough were found, and not because the list ran out."""
        return self.out_of_time or (self.tried >= self.attempts and self.attempts < self.candidates)


async def pick_verified(checker: Checker, candidates: Iterable[str], want: int, https: bool = False,
                        budget: float = BUDGET_SECONDS, on_report: Optional[Callable[[Report], None]] = None,
                        concurrency: int = MAX_CONCURRENCY) -> Selection:
    """Examine candidates in list order until `want` passed, the attempts are used up or `budget` seconds are
    over. At most `concurrency` at a time; cancelling this cancels every check still running."""
    keys = list(dict.fromkeys(candidates))  # a list that names a proxy twice gets it checked once
    attempts = attempts_for(want, len(keys))
    queue = iter(enumerate(keys[:attempts]))
    passed: Dict[int, Report] = {}
    tried = 0
    stopping = False
    enough = asyncio.Event()

    async def worker() -> None:
        nonlocal tried
        for index, key in queue:
            if stopping or len(passed) >= want:
                return
            report = await examine(checker, key)
            if stopping:  # a cancel that an old asyncio.wait_for swallowed (Python < 3.12) still ends it here
                return
            tried += 1
            if on_report:
                on_report(report)
            if report.passes(https):
                passed[index] = report
                if len(passed) >= want:
                    enough.set()

    at_once = concurrency if concurrency < MAX_CONCURRENCY else min(MAX_CONCURRENCY, max(2, want * 2))
    workers = [asyncio.ensure_future(worker()) for _ in range(min(at_once, attempts))]
    waiting = asyncio.ensure_future(enough.wait())
    out_of_time = False
    try:
        if workers:
            # done when every worker is, or as soon as enough passed – the checks still running then are stopped,
            # nobody waits for a slow candidate that is no longer needed
            everyone = asyncio.gather(*workers, return_exceptions=True)
            finished, _ = await asyncio.wait({everyone, waiting}, timeout=budget, return_when=asyncio.FIRST_COMPLETED)
            out_of_time = not finished
    finally:  # also when the caller is cancelled (Ctrl+C): nothing keeps connecting in the background
        stopping = True
        for task in (*workers, waiting):
            task.cancel()
        await asyncio.gather(*workers, waiting, return_exceptions=True)
    verified = [passed[i] for i in sorted(passed)][:want]  # of those that passed, in list order
    return Selection(verified, tried, len(keys), attempts, out_of_time)


def shortfall_message(selection: Selection, want: int, https: bool, checker: Checker) -> str:
    """Why fewer proxies than asked for came out – one line for stderr."""
    got = len(selection.verified)
    what = "passed" + (" (including HTTPS)" if https else "")
    if not checker.confirms:
        return (f"nothing can be verified right now: {checker.confirm_host} did not answer directly, so the "
                "second request could not run. Without --verify you get the list as published")
    if selection.out_of_time:
        why = f"the time limit of {BUDGET_SECONDS:.0f} s ran out after {selection.tried} candidates"
    elif selection.tried >= selection.candidates:
        why = f"all {selection.candidates} matching proxies of the list were tried"
    else:
        why = (f"{selection.tried} of the {selection.candidates} matching proxies were tried "
               "(the limit for one call)")
    return (f"only {got} of {want} {what} from this machine – {why}. Free proxies come and go: try again, "
            "loosen the filters, or run a scan")


def stale_minutes(age_minutes: Optional[int], run_hours: int) -> Optional[int]:
    """How many minutes the list is overdue, None if it is as fresh as it can be."""
    if age_minutes is None:
        return None
    late = age_minutes - run_hours * 60 - STALE_GRACE_MINUTES
    return late if late > 0 else None


# --------------------------------------------------------------------------- text for people

MARK = {PASSED: "✔", FAILED: "✘", UNAVAILABLE: "?", SKIPPED: "–"}


def _measured(report: Report, name: str) -> str:
    check, r = report.checks[name], report.result
    if check.state != PASSED:
        return f"{check.reason}: {REASONS.get(check.reason, check.reason)}" if check.reason else ""
    if name == BASIC:
        return f"exit IP {r.exit_ip}, first answer after {check.ms} ms"
    if name == CONFIRM:
        return f"same exit IP on a second site, anonymity: {r.anonymity}"
    if name == CONTENT:
        return f"static page arrived unchanged ({check.data.get('bytes', '?')} bytes)"
    return f"verified TLS through the tunnel ({check.ms} ms)"


def render(report: Report, notes: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """The diagnosis as (line, state) pairs – state is a check state for the lines about a check, '' otherwise."""
    lines: List[Tuple[str, str]] = [
        (f"Proxy      {shown(report.ptype, report.proxy)}", ""),
        (f"Checked    {report.checks[BASIC].at.replace('T', ' ').replace('+00:00', ' UTC')}, from this machine", ""),
        ("", ""),
    ]
    width = max(len(label) for label in LABELS.values())
    for name in CHECKS:
        check = report.checks[name]
        target = f"  [{check.target}]" if check.target else ""
        lines.append((f" {MARK[check.state]} {LABELS[name]:<{width}}  {check.state:<11}  "
                      f"{_measured(report, name)}{target}", check.state))
    lines += [("", ""), (f"Result     {report.verdict()}", "")]
    limits = [f"{LABELS[name]}: {report.checks[name].limits}" for name in CHECKS if report.checks[name].limits]
    for i, text in enumerate([*notes, *limits]):
        lines.append((f"{'Open' if i == 0 else '    '}       {text}", ""))
    lines.append(("Scope      one measurement, from this network, against the targets in brackets – "
                  "not a promise for later or for other sites", ""))
    return lines


def timed() -> Callable[[], float]:
    start = time.monotonic()
    return lambda: round(time.monotonic() - start, 1)
