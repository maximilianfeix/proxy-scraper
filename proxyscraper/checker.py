"""Proxy checks with our own protocol handshakes (HTTP, SOCKS4, SOCKS5).

Basic check: one TCP connection per proxy, fetching the exit IP from checkip.amazonaws.com.
Confirmation (only for proxies that pass the basic check, so only a few):
  - a second, independent request to httpbin.org/get that has to see the same exit IP – a proxy that
    answers only the check request with "200 + IP" doesn't pass it, nor does an unstable one or an exit
    that changes. The same response shows the headers that arrive and with that the anonymity level.
Detail check:
  - HTTPS: open a tunnel to port 443 and a verified TLS connection inside it – fails for proxies
    that can't CONNECT or that break up TLS (MITM).

Every check leaves a Check on the result (result.checks, see checkstate.py): passed, failed, unavailable or
skipped, with a reason code, the target, the time and what was measured. A check that didn't run is never
"passed", and when a check target itself is down the proxies checked against it are "unavailable", not failed.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .checkstate import (
    BASIC,
    CONFIRM,
    CONTENT,
    FAILED,
    HTTPS,
    LOCAL_ERRNOS,
    PASSED,
    SKIPPED,
    UNAVAILABLE,
    Check,
    CheckFailed,
    legacy_bool,
    now_iso,
    reason_for,
    state_for,
)
from .handshake import Endpoint, parse_endpoint, socks4, socks5, socks5_ipv4, stream_io, with_proxy_auth
from .judges import DEFAULT_JUDGE, Judge
from .netio import USER_AGENT, authority, dechunk, host_header, http_request, read_response, ssl_context
from .parsing import normalize_public_ip, split_key
from .targets import Target

# Check target: returns the IP that reaches the server (plain text, very small).
# Deliberately NOT behind Cloudflare – otherwise any Cloudflare IP would "work" as a fake proxy.
JUDGE_HOST = DEFAULT_JUDGE.host  # for your own IP; checks go through Checker.judge
# Second, independent check target: returns JSON with the sender IP ("origin") and the received headers
CONFIRM_HOST = "httpbin.org"
CONFIRM_PORT = 80
# Deliberately without a Proxy-Connection header – it would show up as a proxy trace itself
_CONFIRM_HEADERS = f"Host: {CONFIRM_HOST}\r\nUser-Agent: {USER_AGENT}\r\nAccept: */*\r\nConnection: close\r\n\r\n"
CONFIRM_REQUEST = f"GET /get HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()
HTTP_PROXY_CONFIRM_REQUEST = f"GET http://{CONFIRM_HOST}/get HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()
# Integrity: a static HTML page that has to arrive through the proxy exactly as it does directly.
# In one early look at 270 proxies, 54 returned a different page; no sample of those pages was kept, so what
# was different about them is not known. content_check records size, hash and <script count from now on.
INTEGRITY_REQUEST = f"GET /html HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()
HTTP_PROXY_INTEGRITY_REQUEST = f"GET http://{CONFIRM_HOST}/html HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()

CONTENT_LENGTH_RE = re.compile(rb"(?im)^content-length:\s*(\d+)")
# At most this many HTTPS/target-site connections at once. Every hit opens 1 + target-site connections
# in parallel – without a limit that quickly adds up to thousands with 2000 workers (EMFILE).
DETAIL_CONNECTIONS = 256
UNREACHABLE_ERRNOS = {errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ENETUNREACH, errno.ETIMEDOUT}
# Headers that give away the proxy (or the client)
PROXY_HEADERS = {
    "via", "x-forwarded-for", "forwarded", "x-real-ip", "client-ip", "x-client-ip",
    "x-proxy-id", "proxy-connection", "x-proxy-connection", "proxy-agent", "x-forwarded-host",
    "x-forwarded-proto", "x-bluecoat-via", "x-originating-ip",
}
ANONYMITY_RANK = {"transparent": 0, "anonymous": 1, "elite": 2}
# A failed confirmation or HTTPS test is only the proxy's failure if the target itself still answers – asked
# directly, after the failure: an answer from before it could predate an outage. The target is asked at most
# every CONTROL_GAP seconds (failures in between wait for the next answer and share it), and an answer that
# says "down" stands for CONTROL_SECONDS.
# reasons of a failed first request that a dead check target would produce just the same
TARGET_DEPENDENT = {"timeout", "bad_status", "connection_closed", "connection_error", "invalid_response",
                    "handshake_refused"}
CONTROL_GAP = 3.0
CONTROL_SECONDS = 10.0
CONTROL_TIMEOUT = 6.0
Control = Callable[[], Awaitable[object]]

# what the results do not say – written next to them, so nobody has to guess
UNCONFIRMED_LIMITS = "no second request ran: a proxy that only answers the first check would look the same"
MISMATCH_LIMITS = ("the second site saw another exit IP: a rotating or chained exit, or a proxy that fakes the "
                   "first answer – this check can't tell which")
CONTENT_LIMITS = ("the bytes differ from the reference: an injected script or ad, a captive portal, a "
                  "re-encoded or cut-off copy – this check doesn't tell which")
HTTPS_LIMITS = ("a verified TLS connection to this one host worked through the proxy at this time – it says "
                "nothing about other sites, later requests or who runs the proxy")


def control_clock() -> float:
    """Seconds for ordering checks and control answers. Not the event loop's clock: that is time.monotonic(),
    which ticks only every ~15.6 ms on Windows before Python 3.13 – a control asked just *before* a check began
    would then carry the same time and pass for an answer asked after it."""
    return time.perf_counter()


async def wait_for(coro, timeout: float):
    """asyncio.wait_for that leaves no unretrieved exception behind when cancelled.

    If a check is cancelled with Ctrl+C while its inner connect is just failing, Python < 3.12
    returns the connection error instead of CancelledError. The inner task then ends with an
    exception nobody retrieves -> "Task exception was never retrieved" plus a traceback on exit.
    The callback retrieves it in any case.
    """
    fut = asyncio.ensure_future(coro)
    fut.add_done_callback(_consume_exception)
    return await asyncio.wait_for(fut, timeout)


def _consume_exception(fut: asyncio.Future) -> None:
    if not fut.cancelled():
        fut.exception()


@dataclass
class CheckResult:
    key: str
    ptype: str
    proxy: str
    latency: int
    exit_ip: str
    https: Optional[bool] = None
    anonymity: str = ""
    country: str = ""
    targets: Dict[str, bool] = field(default_factory=dict)  # target site URL -> reachable?
    asn: int = 0            # provider of the exit IP (DB-IP), 0 = unknown
    org: str = ""
    hosting: Optional[bool] = None  # exit probably in a datacenter? None = unknown
    blocklisted: Optional[bool] = None  # exit IP on the SpamCop blocklist? None = unknown
    speed_kbps: Optional[int] = None  # download speed from the live list (KiB/s), None = not measured
    checked_at: str = ""    # when the basic check finished (ISO 8601, UTC); every check has its own time too
    # check name (basic, confirm, content, https) -> how it ended; a missing name means: never got that far
    checks: Dict[str, Check] = field(default_factory=dict)

    @property
    def url(self) -> str:
        """'socks5://1.2.3.4:1080' – the way curl, requests and friends expect it."""
        return f"{self.ptype}://{self.proxy}"


class Checker:
    def __init__(self, judge_ip: str, own_ips: Iterable[str], timeout: float, connect_timeout: float,
                 confirm_ip: Optional[str] = None, detail_timeout: Optional[float] = None,
                 detail_connect_timeout: Optional[float] = None,
                 targets: Sequence[Tuple[Target, str]] = (), https_test: bool = True,
                 judge: Judge = DEFAULT_JUDGE, integrity_reference: Optional[bytes] = None,
                 confirm_host: str = CONFIRM_HOST, confirm_port: int = CONFIRM_PORT,
                 controls: Optional[Dict[str, Control]] = None):
        self.use_judge(judge, judge_ip)
        # hash of the page as it arrives directly – without a reference there is no tampering check
        self.integrity_reference = integrity_reference
        # without a reachable confirmation target nothing is confirmed (otherwise every proxy would fail) –
        # the results then say "unavailable", not "passed"
        self.confirm_ip_bytes = socket.inet_aton(confirm_ip) if confirm_ip else None
        self.confirm_host, self.confirm_port = confirm_host, confirm_port
        host = host_header(confirm_host, confirm_port, False)
        # deliberately without a Proxy-Connection header – it would show up as a proxy trace itself
        headers = f"Host: {host}\r\nUser-Agent: {USER_AGENT}\r\nAccept: */*\r\nConnection: close\r\n\r\n"
        self.confirm_request = f"GET /get HTTP/1.1\r\n{headers}".encode()
        self.http_proxy_confirm_request = f"GET http://{host}/get HTTP/1.1\r\n{headers}".encode()
        self.integrity_request = f"GET /html HTTP/1.1\r\n{headers}".encode()
        self.http_proxy_integrity_request = f"GET http://{host}/html HTTP/1.1\r\n{headers}".encode()
        # "does the target still answer directly?" per check: CONFIRM and HTTPS return true/false, CONTENT
        # returns the reference hash as it is now (None = unreachable). Without one, a failure is taken as it is.
        self.controls: Dict[str, Control] = dict(controls or {})
        self._control_cache: Dict[str, Tuple[float, asyncio.Future]] = {}  # name -> (asked at, answer)
        self.https_port = 443
        self.tls_context: Optional[ssl.SSLContext] = None  # None = certifi's roots
        self.failures: Counter = Counter()  # "failed:reason" -> basic checks that ended that way
        self.no_verdict: Set[str] = set()  # keys whose basic check was "unavailable"; whoever reads it removes it
        # the local test lab hands out documentation addresses (203.0.113.x) as exit IPs; real runs never accept them
        self.reserved_exit_ips_ok = False
        # several possible: e.g. the real IP via HTTPS, but iCloud Private Relay or a corporate proxy on port 80
        self.own_ips = set(own_ips)
        self.timeout = timeout
        self._detail_slots: Optional[asyncio.Semaphore] = None
        self.https_test = https_test  # --fast: no HTTPS test, target sites still
        # target sites with a pre-resolved IP (SOCKS4 can't do host names)
        self.targets = [(target, socket.inet_aton(ip)) for target, ip in targets]
        # confirmation and HTTPS test may take longer than the (possibly latency-limited) basic check
        self.detail_timeout = detail_timeout or timeout
        self.detail_connect_timeout = min(detail_connect_timeout or connect_timeout, self.detail_timeout)
        # the vast majority of dead proxies already fail at the TCP connect – they shouldn't
        # block a slot for the full timeout.
        self.connect_timeout = min(connect_timeout, timeout)
        self.unreachable: Set[str] = set()

    def use_judge(self, judge: Judge, ip: str) -> None:
        """Set the check target or switch it mid-run (running checks still use the old one)."""
        self.judge = judge
        self.judge_ip = ip
        self.judge_ip_bytes = socket.inet_aton(ip)
        self.request = (
            f"GET {judge.path} HTTP/1.1\r\nHost: {judge.authority}\r\nUser-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        # HTTP proxies need the absolute URL
        self.http_proxy_request = (
            f"GET http://{judge.authority}{judge.path} HTTP/1.1\r\nHost: {judge.authority}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\nProxy-Connection: close\r\n\r\n"
        ).encode()

    @property
    def confirms(self) -> bool:
        return self.confirm_ip_bytes is not None

    # ------------------------------------------------------------------ basic check

    async def check(self, key: str) -> Optional[CheckResult]:
        """Working proxy -> CheckResult, otherwise None (check_detailed also says why)."""
        return (await self.check_detailed(key))[0]

    async def check_detailed(self, key: str) -> Tuple[Optional[CheckResult], Check]:
        """The basic check with its outcome: (result, check) for a working proxy, (None, check) otherwise."""
        ptype, proxy = split_key(key)
        judge = self.judge
        target = authority(judge.host, judge.port)
        began = control_clock()
        start = time.perf_counter()
        reason, exit_ip = "", ""
        connected: List[bool] = []
        try:
            body = await wait_for(self._check(ptype, proxy, connected), self.timeout)
        except Exception as e:  # timeout, connection error, broken response – all mean "no good"
            reason = reason_for(e)
            if reason == "timeout" and not connected:
                # the time ran out during the TCP connect (with connect timeout = timeout the outer limit can
                # fire first; Windows also retries a refused localhost port for ~2 s): the proxy never answered
                reason = "connect_timeout"
        else:
            if body is None:
                reason = "bad_status"
            else:
                exit_ip = body.strip().decode("ascii", "ignore")
                try:
                    ipaddress.IPv4Address(exit_ip)
                except ValueError:
                    reason, exit_ip = "invalid_response", ""  # garbage/ads/a login page -> unusable
                else:
                    if not self.reserved_exit_ips_ok and normalize_public_ip(exit_ip.encode()) != exit_ip:
                        reason = "private_exit_ip"  # 127.0.0.1, 10.x and the like – the proxy answers itself
                    elif exit_ip in self.own_ips:
                        reason = "own_ip_exposed"  # transparent proxy reveals your real IP
        ms = round((time.perf_counter() - start) * 1000)
        data = {"exit_ip": exit_ip} if exit_ip else {}
        if reason:
            state = state_for(reason)
            # only where a control is set (--diagnose, --pick --verify): a scan has JudgeWatch for this. Whatever
            # fails before the proxy talks to the target (no connection, a refused login) is the proxy's either way
            if (state == FAILED and BASIC in self.controls and reason in TARGET_DEPENDENT
                    and await self._target_ok(BASIC, began) is False):
                state, reason = UNAVAILABLE, "target_unreachable"
            check = Check(state, reason, target, now_iso(), ms, data)
            self.failures[check.label()] += 1
            if state == UNAVAILABLE:
                self.no_verdict.add(key)  # for callers of check(), which only see None: this one isn't a failure
            return None, check
        check = Check(PASSED, "", target, now_iso(), ms, data)
        result = CheckResult(key, ptype, proxy, ms, exit_ip, checked_at=check.at)
        result.checks[BASIC] = check
        return result, check

    async def _check(self, ptype: str, proxy: str, connected: Optional[List[bool]] = None):
        # Many ip:port entries appear under several types in the lists – whatever fails at the
        # TCP connect fails for the other types just the same.
        ep = parse_endpoint(proxy)
        if ep.address in self.unreachable:
            raise CheckFailed("known_unreachable")
        # keep target IP and request together – if the check target changes mid-way, both still match
        ip_bytes, port = self.judge_ip_bytes, self.judge.port
        request = self.http_proxy_request if ptype == "http" else self.request
        reader, writer = await self._connect_or_fail(proxy)
        if connected is not None:
            connected.append(True)
        try:
            if not await self._handshake(ptype, ep, reader, writer, ip_bytes, port):
                raise CheckFailed("handshake_refused")
            writer.write(with_proxy_auth(request, ep) if ptype == "http" else request)
            await writer.drain()
            return await _read_http_200(reader)
        finally:
            writer.close()

    async def _connect_or_fail(self, proxy: str, detail: bool = False):
        """_connect, with the reason a connection didn't come about as a CheckFailed."""
        try:
            return await self._connect(proxy, detail)
        except asyncio.TimeoutError:
            raise CheckFailed("connect_timeout") from None
        except ConnectionRefusedError:
            raise CheckFailed("connect_refused") from None
        except OSError as e:
            if e.errno in LOCAL_ERRNOS:
                raise  # our shortage, not the proxy's
            raise CheckFailed("connect_failed") from None

    async def _connect(self, proxy: str, detail: bool = False):
        """TCP connection to the proxy. Only the basic check remembers unreachable proxies and uses the
        (possibly latency-limited) short timeout – detail checks get the normal one."""
        ep = parse_endpoint(proxy)
        timeout = self.detail_connect_timeout if detail else self.connect_timeout
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ep.host, ep.port), timeout)
        except (asyncio.TimeoutError, ConnectionRefusedError):
            if not detail:
                self.unreachable.add(ep.address)
            raise
        except OSError as e:
            # not e.g. EMFILE – that's our fault, not the proxy's
            if not detail and e.errno in UNREACHABLE_ERRNOS:
                self.unreachable.add(ep.address)
            raise
        return reader, writer

    async def _handshake(self, ptype: str, ep: Endpoint, reader, writer, ip_bytes: bytes, port: int) -> bool:
        """Open a SOCKS connection to ip:port; HTTP proxies don't need a handshake."""
        send, recv_exact = stream_io(reader, writer)
        if ptype == "socks4":
            return await socks4(send, recv_exact, ep, ip_bytes, port)
        if ptype == "socks5":
            return await socks5(send, recv_exact, ep, socks5_ipv4(ip_bytes), port)
        return True

    # ------------------------------------------------------------------ confirmation

    async def confirm(self, result: CheckResult) -> bool:
        """A second, independent request through the same proxy. False = it ran and did not confirm the proxy.

        True does not mean "confirmed": without a reachable confirmation target the check is unavailable and
        the proxy is kept – result.checks["confirm"] says which of the two it was. Also sets the anonymity
        level from the headers that reach the target.
        """
        check = result.checks[CONFIRM] = await self.confirm_check(result)
        return check.state != FAILED

    async def confirm_check(self, result: CheckResult) -> Check:
        target = authority(self.confirm_host, self.confirm_port)
        if not self.confirms:
            return Check(UNAVAILABLE, "target_not_configured", target, now_iso(), limits=UNCONFIRMED_LIMITS)
        began = control_clock()
        start = time.perf_counter()
        reason, data = "", {}
        try:
            body = await wait_for(self._confirm(result.ptype, result.proxy), self.detail_timeout)
        except Exception as e:  # an error on the second request means: not reliable
            reason = reason_for(e)
        else:
            origins = confirmation_origins(body) if body is not None else None
            if body is None:
                reason = "bad_status"
            elif origins is None:
                reason = "invalid_response"
            elif result.exit_ip not in origins:
                reason, data = "exit_ip_mismatch", {"exit_ip": result.exit_ip, "second_exit_ip": origins[-1]}
            else:
                anonymity = classify_anonymity(body, self.own_ips)
                if anonymity is None:
                    reason = "invalid_response"
                else:
                    result.anonymity = anonymity
                    data = {"exit_ip": result.exit_ip, "anonymity": anonymity}
        ms = round((time.perf_counter() - start) * 1000)
        if not reason:
            return Check(PASSED, "", target, now_iso(), ms, data)
        state = state_for(reason)
        # a second site that saw another exit IP did answer; for anything else, the target may be the one
        # that is down – then nothing was learned about this proxy
        if state == FAILED and reason != "exit_ip_mismatch" and await self._target_ok(CONFIRM, began) is False:
            return Check(UNAVAILABLE, "target_unreachable", target, now_iso(), ms, limits=UNCONFIRMED_LIMITS)
        return Check(state, reason, target, now_iso(), ms, data,
                     limits=MISMATCH_LIMITS if reason == "exit_ip_mismatch" else "")

    async def _confirm(self, ptype: str, proxy: str, request: Optional[bytes] = None,
                       http_proxy_request: Optional[bytes] = None) -> Optional[bytes]:
        ep = parse_endpoint(proxy)
        request = request or self.confirm_request
        http_proxy_request = http_proxy_request or self.http_proxy_confirm_request
        reader, writer = await self._connect_or_fail(proxy, detail=True)
        try:
            if not await self._handshake(ptype, ep, reader, writer, self.confirm_ip_bytes, self.confirm_port):
                raise CheckFailed("handshake_refused")
            writer.write(with_proxy_auth(http_proxy_request, ep) if ptype == "http" else request)
            await writer.drain()
            # the response comes from the (untrusted) proxy – read only a limited amount
            return await _read_http_200(reader)
        finally:
            writer.close()

    async def tampers(self, result: CheckResult) -> bool:
        """Does a known page arrive with different bytes? True only for a page that came back and differs –
        timeouts or error pages say nothing about that (result.checks["content"] is then "unavailable")."""
        check = result.checks[CONTENT] = await self.content_check(result)
        return check.state == FAILED

    async def content_check(self, result: CheckResult) -> Check:
        target = f"{authority(self.confirm_host, self.confirm_port)}/html"
        if not self.confirms:
            return Check(UNAVAILABLE, "target_not_configured", target, now_iso())
        if self.integrity_reference is None:
            return Check(UNAVAILABLE, "no_reference", target, now_iso())
        began = control_clock()
        start = time.perf_counter()
        try:
            body = await wait_for(self._confirm(result.ptype, result.proxy, self.integrity_request,
                                                self.http_proxy_integrity_request), self.detail_timeout)
        except Exception as e:  # no page, no comparison
            return Check(UNAVAILABLE, reason_for(e), target, now_iso(), round((time.perf_counter() - start) * 1000))
        ms = round((time.perf_counter() - start) * 1000)
        if body is None:
            return Check(UNAVAILABLE, "bad_status", target, now_iso(), ms)
        digest = page_hash(body)
        if digest != self.integrity_reference and CONTENT in self.controls:
            # the page may have changed at its source since the run started: compare with how it is now
            current = await self._control(CONTENT, began)
            if not isinstance(current, bytes):
                return Check(UNAVAILABLE, "target_unreachable", target, now_iso(), ms)
            self.integrity_reference = current
        if digest == self.integrity_reference:
            return Check(PASSED, "", target, now_iso(), ms, {"bytes": len(body)})
        data = {"bytes": len(body), "sha256": digest.hex()[:16], "script_tags": body.lower().count(b"<script")}
        return Check(FAILED, "content_mismatch", target, now_iso(), ms, data, limits=CONTENT_LIMITS)

    # ------------------------------------------------------------------ is the target itself still there?

    async def _control(self, name: str, since: float):
        """What this check's target says when asked directly, for a check that began at `since` (control_clock()) and
        failed. None on an error.

        Only an answer asked for after the check began counts as "fine" – an older one says nothing about a
        target that went down in between. Without one, this waits for the next time the target is asked (at
        most CONTROL_GAP seconds away) and shares that answer with everyone else who is waiting. "Down" is
        believed for CONTROL_SECONDS without asking again: it costs a proxy nothing but an "unavailable".
        What stays possible: a target that dies between that answer and the proxy's own request, within one
        check's duration."""
        now = control_clock()
        cached = self._control_cache.get(name)
        if cached is not None:
            asked_at, answer = cached
            if asked_at >= since:  # asked (or about to be) after this check began
                return await asyncio.shield(answer)
            if answer.done() and not answer.cancelled() and not answer.result() and now - asked_at < CONTROL_SECONDS:
                return answer.result()
        ask_at = max(now, cached[0] + CONTROL_GAP) if cached is not None else now
        answer = asyncio.ensure_future(self._run_control(self.controls[name], ask_at - now))
        answer.add_done_callback(_consume_exception)
        self._control_cache[name] = (ask_at, answer)
        # shielded: one cancelled check mustn't take the answer away from the others waiting for it
        return await asyncio.shield(answer)

    async def _run_control(self, control: Control, delay: float = 0.0):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            return await asyncio.wait_for(control(), min(self.detail_timeout, CONTROL_TIMEOUT))
        except Exception:  # unreachable, a timeout, a broken answer – the target isn't fine
            return None

    async def _target_ok(self, name: str, since: float) -> Optional[bool]:
        """True/False from the control, None when there is none (then a failure is taken as it is)."""
        if name not in self.controls:
            return None
        return bool(await self._control(name, since))

    # ------------------------------------------------------------------ details

    async def enrich(self, result: CheckResult) -> None:
        """Add HTTPS support and target sites, all in parallel (anonymity comes from the confirmation)."""
        https = self.https_check(result) if self.https_test else _none()
        outcomes = await asyncio.gather(
            https,
            *(self._safe(self.check_target(result.ptype, result.proxy, t, ip)) for t, ip in self.targets),
        )
        check = outcomes[0] or Check(SKIPPED, "fast_mode", at=now_iso())
        result.checks[HTTPS] = check
        result.https = legacy_bool(check)  # true/false only when it was measured
        result.targets = {t.url: bool(ok) for (t, _), ok in zip(self.targets, outcomes[1:])}

    def _slots(self) -> asyncio.Semaphore:
        if self._detail_slots is None:  # only here: before Python 3.10 a semaphore is bound to the event loop
            self._detail_slots = asyncio.Semaphore(DETAIL_CONNECTIONS)
        return self._detail_slots

    async def _safe(self, coro):
        try:
            async with self._slots():
                return await wait_for(coro, self.detail_timeout)
        except Exception:  # detail check failed -> "no"/"unknown", the basic result stays
            return None

    async def https_check(self, result: CheckResult) -> Check:
        """The HTTPS test with its outcome. Passed means: HTTPS_LIMITS, and nothing beyond that."""
        target = authority(self.judge.host, self.https_port)
        began = control_clock()
        start = time.perf_counter()
        try:
            async with self._slots():
                ok = await wait_for(self.check_https(result.ptype, result.proxy), self.detail_timeout)
            reason = "" if ok else "invalid_response"
        except Exception as e:
            reason = reason_for(e)
        ms = round((time.perf_counter() - start) * 1000)
        if not reason:
            return Check(PASSED, "", target, now_iso(), ms, limits=HTTPS_LIMITS)
        state = state_for(reason)
        # the same request directly, certificate check included: if that fails too, it isn't the proxy
        if state == FAILED and await self._target_ok(HTTPS, began) is False:
            state, reason = UNAVAILABLE, "target_unreachable"
        return Check(state, reason, target, now_iso(), ms)

    async def check_https(self, ptype: str, proxy: str) -> bool:
        """Tunnel to the check target on port 443 + verified TLS + fetch the exit IP. False for a wrong
        answer inside the tunnel; a refused tunnel or a failed TLS handshake raises (CheckFailed, SSLError)."""
        judge, ip_bytes, request = self.judge, self.judge_ip_bytes, self.request  # in case it switches mid-way
        reader, writer = await self._open_tls(ptype, proxy, judge.host, ip_bytes, self.https_port)
        try:
            writer.write(request)
            await writer.drain()
            # after verified TLS the real server is talking here, not the proxy
            status, _, body = await read_response(reader)
        finally:
            writer.close()
        try:
            ipaddress.IPv4Address(body.strip().decode("ascii", "ignore"))
        except ValueError:
            return False
        return status == 200

    async def check_target(self, ptype: str, proxy: str, target: Target, ip_bytes: bytes) -> bool:
        """A real request to a target site through the proxy; 2xx/3xx = reachable.

        Only the response head is read – nobody needs to download a 500 KB home page.
        """
        request = (
            f"GET {{path}} HTTP/1.1\r\nHost: {target.host_header}\r\nUser-Agent: {USER_AGENT}\r\n"
            f"Accept: text/html,*/*;q=0.8\r\nAccept-Language: en-US,en;q=0.8\r\nConnection: close\r\n\r\n"
        )
        if target.tls:
            opened = await self._tls_tunnel(ptype, proxy, target.host, ip_bytes, target.port)
            if opened is None:
                return False
            reader, writer = opened
            path = target.path
        else:
            reader, writer = await self._connect(proxy, detail=True)
            # HTTP proxies want the absolute URL for plain HTTP
            path = target.url if ptype == "http" else target.path
        ep = parse_endpoint(proxy)
        try:
            # handshake inside the try: if it fails with an exception, the socket is still closed
            if not target.tls and not await self._handshake(ptype, ep, reader, writer, ip_bytes, target.port):
                return False
            data = request.format(path=path).encode()
            writer.write(with_proxy_auth(data, ep) if ptype == "http" and not target.tls else data)
            await writer.drain()
            status = await _read_status(reader)
        finally:
            writer.close()
        return 200 <= status < 400

    async def tls_tunnel(self, ptype: str, proxy: str, host: str, ip: str, port: int = 443):
        """Public side of _tls_tunnel for the steps after a run (sites, speed): ip as text."""
        return await self._tls_tunnel(ptype, proxy, host, socket.inet_aton(ip), port)

    async def _tls_tunnel(self, ptype: str, proxy: str, host: str, ip_bytes: bytes, port: int):
        """Tunnel through the proxy to host:port with verified TLS inside. None = tunnel refused or MITM."""
        try:
            return await self._open_tls(ptype, proxy, host, ip_bytes, port)
        except (CheckFailed, ssl.SSLCertVerificationError):
            return None

    async def _open_tls(self, ptype: str, proxy: str, host: str, ip_bytes: bytes, port: int):
        """Like _tls_tunnel, but says why it didn't work: CheckFailed("tunnel_refused"), or the
        SSLCertVerificationError of a proxy that breaks up TLS (MITM) – useless for HTTPS either way."""
        loop = asyncio.get_running_loop()
        ep = parse_endpoint(proxy)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            await loop.sock_connect(sock, (ep.host, ep.port))
            if not await self._open_tunnel(loop, sock, ptype, ep, host, ip_bytes, port):
                raise CheckFailed("tunnel_refused")
            return await asyncio.open_connection(sock=sock, ssl=self.tls_context or ssl_context(),
                                                 server_hostname=host)
        except BaseException:
            sock.close()
            raise

    async def _open_tunnel(self, loop, sock: socket.socket, ptype: str, ep: Endpoint, host: str,
                           ip_bytes: bytes, port: int) -> bool:
        async def recv_exact(n: int) -> bytes:
            buf = b""
            while len(buf) < n:
                chunk = await loop.sock_recv(sock, n - len(buf))
                if not chunk:
                    raise ConnectionError("connection closed")
                buf += chunk
            return buf

        if ptype == "http":
            target = authority(host, port)
            connect = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode()
            await loop.sock_sendall(sock, with_proxy_auth(connect, ep))
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 8192:
                chunk = await loop.sock_recv(sock, 1)  # byte by byte: don't swallow anything of the TLS stream
                if not chunk:
                    return False
                head += chunk
            first = head.split(b"\r\n", 1)[0]
            return first.startswith(b"HTTP/") and b" 200" in first

        async def send(data: bytes) -> None:
            await loop.sock_sendall(sock, data)

        if ptype == "socks4":
            return await socks4(send, recv_exact, ep, ip_bytes, port)
        return await socks5(send, recv_exact, ep, socks5_ipv4(ip_bytes), port)


async def _none() -> None:
    return None


async def _read_status(reader) -> int:
    """Read only the status code of an HTTP response (head at most 64 KiB)."""
    head = await reader.readuntil(b"\r\n\r\n")
    parts = head.split(b"\r\n", 1)[0].split()
    return int(parts[1]) if len(parts) > 1 and parts[0].startswith(b"HTTP/") and parts[1].isdigit() else 0


def confirmation_origins(body: bytes) -> Optional[List[str]]:
    """IPs from an httpbin response ("origin": "1.2.3.4" or "1.2.3.4, 5.6.7.8"), None if unusable."""
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):  # also absurdly nested JSON – the answer comes from a stranger's proxy
        return None
    # httpbin always returns "origin" and "headers" – if one is missing, it's not the expected response
    if not isinstance(data, dict) or not isinstance(data.get("headers"), dict):
        return None
    origins = [part.strip() for part in str(data.get("origin", "")).split(",")]
    return [o for o in origins if _is_ipv4(o)] or None


def classify_confirmation(body: bytes, own_ips: Iterable[str], exit_ip: str) -> Optional[str]:
    """Check the response from httpbin.org/get -> anonymity level, or None for an unusable response.

    A proxy that only answers the first check doesn't return JSON with a valid sender IP here. The proxy
    also has to show the same exit IP on both requests – rotating or chained exits aren't reliable.
    """
    origins = confirmation_origins(body)
    if origins is None or exit_ip not in origins:
        return None
    return classify_anonymity(body, own_ips)


async def probe_confirm_target(ip: str, timeout: float, port: int = CONFIRM_PORT) -> bool:
    """Does `ip` answer directly (without a proxy) exactly the way the confirmation expects?

    The same request, the same size limit, the same evaluation – and exactly the IP that is used
    later. A redirect (e.g. to HTTPS), a captive portal or an error page doesn't count.
    """
    async def probe() -> Optional[bytes]:
        reader, writer = await asyncio.open_connection(ip, port)
        try:
            writer.write(CONFIRM_REQUEST)
            await writer.drain()
            return await _read_http_200(reader)
        finally:
            writer.close()

    try:
        body = await wait_for(probe(), timeout)
    except Exception:  # unreachable -> continue without confirmation
        return False
    return body is not None and confirmation_origins(body) is not None


async def probe_https_target(host: str, ip: str, port: int = 443, context: Optional[ssl.SSLContext] = None,
                             timeout: float = CONTROL_TIMEOUT, request: Optional[bytes] = None) -> bool:
    """Does the HTTPS test's target do directly (without a proxy) what the test expects through one: a TLS
    handshake that verifies and, given the test's request, a 200 with an IP address?"""
    async def probe() -> bool:
        reader, writer = await asyncio.open_connection(ip, port, ssl=context or ssl_context(),
                                                       server_hostname=host)
        try:
            if request is None:
                return True
            writer.write(request)
            await writer.drain()
            status, _, body = await read_response(reader)
            return status == 200 and _is_ipv4(body.strip().decode("ascii", "ignore"))
        finally:
            writer.close()

    try:
        return await asyncio.wait_for(probe(), timeout)
    except Exception:  # unreachable, a certificate that doesn't verify, a broken answer
        return False


def direct_controls(checker: "Checker", confirm_ip: Optional[str]) -> Dict[str, Control]:
    """The controls of a normal run: each asks the check's own target directly, the way the check does.
    Read from the checker at call time – the check target can switch during a run."""
    controls: Dict[str, Control] = {
        HTTPS: lambda: probe_https_target(checker.judge.host, checker.judge_ip, checker.https_port,
                                          checker.tls_context, request=checker.request),
    }
    if confirm_ip:
        controls[CONFIRM] = lambda: probe_confirm_target(confirm_ip, CONTROL_TIMEOUT, checker.confirm_port)
        controls[CONTENT] = lambda: integrity_reference(CONTROL_TIMEOUT)
    return controls


def page_hash(body: bytes) -> bytes:
    return hashlib.sha256(body).digest()


async def integrity_reference(timeout: float, fetch=None) -> Optional[bytes]:
    """Hash of the reference page, fetched directly – over verified HTTPS. Over HTTP a captive portal
    or a filter on your own network could already falsify the reference. Both ways return the same bytes."""
    try:
        status, _, body = await (fetch or http_request)(f"https://{CONFIRM_HOST}/html", timeout=timeout,
                                                        max_redirects=0, insecure_fallback=False)
    except Exception:
        return None
    return page_hash(body) if status == 200 and body else None


def _is_ipv4(text: str) -> bool:
    try:
        ipaddress.IPv4Address(text)
        return True
    except ValueError:
        return False


def _contains_ip(body: bytes, ip: str) -> bool:
    """The whole address, not a piece of a longer one: 1.2.3.4 is not in 11.2.3.45."""
    return re.search(rb"(?<![\d.])" + re.escape(ip.encode()) + rb"(?![\d.])", body) is not None


def classify_anonymity(body: bytes, own_ips: Iterable[str]) -> Optional[str]:
    """Response from httpbin.org (with "headers") -> transparent / anonymous / elite."""
    if any(ip and _contains_ip(body, ip) for ip in own_ips):
        return "transparent"
    try:
        headers = json.loads(body).get("headers", {})
    except (ValueError, AttributeError, RecursionError):
        return None
    if not isinstance(headers, dict):
        return None  # unexpected response – don't crash, just don't confirm
    names = {str(name).lower() for name in headers}
    return "anonymous" if names & PROXY_HEADERS else "elite"


async def _read_http_200(reader) -> Optional[bytes]:
    """Read a small HTTP response; the body only for status 200, otherwise None."""
    data = bytearray()
    want = None  # total length from Content-Length, once the header is there
    while len(data) < 16384:
        try:
            chunk = await reader.read(4096)
        except ConnectionResetError:
            break
        if not chunk:
            break
        data += chunk
        if want is None:
            end = data.find(b"\r\n\r\n")
            if end >= 0:
                if not data.startswith(b"HTTP/") or b" 200" not in data[: data.find(b"\r\n")]:
                    return None  # bail out early, the rest of the response doesn't matter
                m = CONTENT_LENGTH_RE.search(data, 0, end)
                want = end + 4 + int(m.group(1)) if m else -1
        if want is not None and 0 <= want <= len(data):
            break

    head, _, body = bytes(data).partition(b"\r\n\r\n")
    if not head.startswith(b"HTTP/") or b" 200" not in head.split(b"\r\n", 1)[0]:
        return None
    if b"chunked" in head.lower():
        body = dechunk(body)
    return body
