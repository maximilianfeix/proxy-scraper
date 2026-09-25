"""Proxy checks with our own protocol handshakes (HTTP, SOCKS4, SOCKS5).

Basic check: one TCP connection per proxy, fetching the exit IP from checkip.amazonaws.com.
Confirmation (only for proxies that pass the basic check, so only a few):
  - a second, independent request to httpbin.org/get – filters out honeypots that answer only the
    check request with "200 + IP" and reject everything else. The same response shows the headers
    that arrive and with that the anonymity level.
Detail check:
  - HTTPS: open a tunnel to port 443 and a verified TLS connection inside it – fails for proxies
    that can't CONNECT or that break up TLS (MITM).
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
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .handshake import Endpoint, parse_endpoint, socks4, socks5, socks5_ipv4, stream_io, with_proxy_auth
from .judges import DEFAULT_JUDGE, Judge
from .netio import USER_AGENT, dechunk, http_request, read_response, ssl_context
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
# Measured on 270 working proxies, 54 (20 %) returned a modified page – mostly with an injected
# <script src="http://…">.
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

    @property
    def url(self) -> str:
        """'socks5://1.2.3.4:1080' – the way curl, requests and friends expect it."""
        return f"{self.ptype}://{self.proxy}"


class Checker:
    def __init__(self, judge_ip: str, own_ips: Iterable[str], timeout: float, connect_timeout: float,
                 confirm_ip: Optional[str] = None, detail_timeout: Optional[float] = None,
                 detail_connect_timeout: Optional[float] = None,
                 targets: Sequence[Tuple[Target, str]] = (), https_test: bool = True,
                 judge: Judge = DEFAULT_JUDGE, integrity_reference: Optional[bytes] = None):
        self.use_judge(judge, judge_ip)
        # hash of the page as it arrives directly – without a reference there is no tampering check
        self.integrity_reference = integrity_reference
        # without a reachable confirmation target nothing is confirmed (otherwise every proxy would fail)
        self.confirm_ip_bytes = socket.inet_aton(confirm_ip) if confirm_ip else None
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
        """Working proxy -> CheckResult, otherwise None."""
        ptype, proxy = split_key(key)
        start = time.perf_counter()
        try:
            body = await wait_for(self._check(ptype, proxy), self.timeout)
        except Exception:  # timeout, connection error, broken response – all mean "no good"
            return None

        if body is None:
            return None
        exit_ip = body.strip().decode("ascii", "ignore")
        try:
            ipaddress.IPv4Address(exit_ip)
        except ValueError:
            return None  # proxy returns garbage/ads/a login page -> unusable
        if normalize_public_ip(exit_ip.encode()) != exit_ip:
            return None  # 127.0.0.1, 10.x and the like aren't a real exit IP – the proxy answers itself
        if exit_ip in self.own_ips:
            return None  # transparent proxy reveals your real IP
        return CheckResult(key, ptype, proxy, round((time.perf_counter() - start) * 1000), exit_ip)

    async def _check(self, ptype: str, proxy: str):
        # Many ip:port entries appear under several types in the lists – whatever fails at the
        # TCP connect fails for the other types just the same.
        ep = parse_endpoint(proxy)
        if ep.address in self.unreachable:
            return None
        # keep target IP and request together – if the check target changes mid-way, both still match
        ip_bytes, port = self.judge_ip_bytes, self.judge.port
        request = self.http_proxy_request if ptype == "http" else self.request
        reader, writer = await self._connect(proxy)
        try:
            if not await self._handshake(ptype, ep, reader, writer, ip_bytes, port):
                return None
            writer.write(with_proxy_auth(request, ep) if ptype == "http" else request)
            await writer.drain()
            return await _read_http_200(reader)
        finally:
            writer.close()

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
        """A second, independent request through the same proxy. False = fake/honeypot or unstable.

        Also sets the anonymity level from the headers that reach the target.
        """
        if not self.confirms:
            return True
        try:
            body = await wait_for(self._confirm(result.ptype, result.proxy), self.detail_timeout)
        except Exception:  # an error on the second request means: not reliable
            return False
        anonymity = classify_confirmation(body, self.own_ips, result.exit_ip) if body is not None else None
        if anonymity is None:
            return False
        result.anonymity = anonymity
        return True

    async def _confirm(self, ptype: str, proxy: str, request: bytes = CONFIRM_REQUEST,
                       http_proxy_request: bytes = HTTP_PROXY_CONFIRM_REQUEST) -> Optional[bytes]:
        ep = parse_endpoint(proxy)
        reader, writer = await self._connect(proxy, detail=True)
        try:
            if not await self._handshake(ptype, ep, reader, writer, self.confirm_ip_bytes, CONFIRM_PORT):
                return None
            writer.write(with_proxy_auth(http_proxy_request, ep) if ptype == "http" else request)
            await writer.drain()
            # the response comes from the (untrusted) proxy – read only a limited amount
            return await _read_http_200(reader)
        finally:
            writer.close()

    async def tampers(self, result: CheckResult) -> bool:
        """Does the proxy modify content (ads, scripts)? True only for a clearly modified page –
        timeouts or error pages say nothing about that, the other checks cover those."""
        if self.integrity_reference is None or not self.confirms:
            return False
        try:
            body = await wait_for(self._confirm(result.ptype, result.proxy, INTEGRITY_REQUEST,
                                                HTTP_PROXY_INTEGRITY_REQUEST), self.detail_timeout)
        except Exception:
            return False
        return body is not None and page_hash(body) != self.integrity_reference

    # ------------------------------------------------------------------ details

    async def enrich(self, result: CheckResult) -> None:
        """Add HTTPS support and target sites, all in parallel (anonymity comes from the confirmation)."""
        https = self._safe(self.check_https(result.ptype, result.proxy)) if self.https_test else _none()
        outcomes = await asyncio.gather(
            https,
            *(self._safe(self.check_target(result.ptype, result.proxy, t, ip)) for t, ip in self.targets),
        )
        result.https = bool(outcomes[0]) if self.https_test else None
        result.targets = {t.url: bool(ok) for (t, _), ok in zip(self.targets, outcomes[1:])}

    async def _safe(self, coro):
        if self._detail_slots is None:  # only here: before Python 3.10 a semaphore is bound to the event loop
            self._detail_slots = asyncio.Semaphore(DETAIL_CONNECTIONS)
        try:
            async with self._detail_slots:
                return await wait_for(coro, self.detail_timeout)
        except Exception:  # detail check failed -> "no"/"unknown", the basic result stays
            return None

    async def check_https(self, ptype: str, proxy: str) -> bool:
        """Tunnel to the check target on port 443 + verified TLS + fetch the exit IP."""
        judge, ip_bytes, request = self.judge, self.judge_ip_bytes, self.request  # in case it switches mid-way
        opened = await self._tls_tunnel(ptype, proxy, judge.host, ip_bytes, 443)
        if opened is None:
            return False
        reader, writer = opened
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

    async def _tls_tunnel(self, ptype: str, proxy: str, host: str, ip_bytes: bytes, port: int):
        """Tunnel through the proxy to host:port with verified TLS inside. None = tunnel refused or MITM."""
        loop = asyncio.get_running_loop()
        ep = parse_endpoint(proxy)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            await loop.sock_connect(sock, (ep.host, ep.port))
            if not await self._open_tunnel(loop, sock, ptype, ep, host, ip_bytes, port):
                sock.close()
                return None
            return await asyncio.open_connection(sock=sock, ssl=ssl_context(), server_hostname=host)
        except ssl.SSLCertVerificationError:
            sock.close()
            return None  # proxy breaks up TLS (MITM) -> useless for HTTPS
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
            connect = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode()
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
    except ValueError:
        return None
    # httpbin always returns "origin" and "headers" – if one is missing, it's not the expected response
    if not isinstance(data, dict) or not isinstance(data.get("headers"), dict):
        return None
    origins = [part.strip() for part in str(data.get("origin", "")).split(",")]
    return [o for o in origins if _is_ipv4(o)] or None


def classify_confirmation(body: bytes, own_ips: Iterable[str], exit_ip: str) -> Optional[str]:
    """Check the response from httpbin.org/get -> anonymity level, or None for an unusable response.

    Honeypots don't return JSON with a valid sender IP here. The proxy also has to show the same
    exit IP on both requests – rotating or chained exits aren't reliable.
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
    except (ValueError, AttributeError):
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
