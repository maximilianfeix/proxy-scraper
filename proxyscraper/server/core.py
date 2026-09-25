"""Local rotating proxy server (--serve).

Accepts HTTP proxy requests (CONNECT for HTTPS and plain HTTP requests) and sends every
connection through one of the proxies that were found. Fast, reliable proxies are preferred;
if one fails, the next one is tried automatically, and one that fails several times in a row
drops out of the rotation.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Set, Tuple

from ..handshake import parse_endpoint, with_proxy_auth
from .http import (
    TLS_HANDSHAKE,
    ResponseScreen,
    forward_request,
    origin_request,
    parse_request_head,
    plausible_answer,
    request_body_length,
)
from .pool import ANY, ProxyPool, Selection
from .socks import SOCKS5_VERSION, Socks5Refused, socks5_accept, socks5_reply
from .status import (
    METRICS_PATH,
    METRICS_TYPE,
    STATUS_PATH,
    STATUS_PREFIX,
    metrics_text,
    password_ok,
    selection_from_headers,
    status_json,
)
from .upstream import TargetError, Unsupported, UpstreamError, open_upstream

MAX_ATTEMPTS = 3            # this many proxies per request before the client gets an error
FIRST_CHUNK_WAIT = 5.0      # how long to wait for the client's first packet in the tunnel
MAX_REPLAY_BODY = 1024 * 1024  # request bodies up to this size are buffered for switching proxies
HTTP_ESTABLISHED = b"HTTP/1.1 200 Connection established\r\n\r\n"
HEAD_LIMIT = 64 * 1024


@dataclass
class RequestLog:
    client: str
    target: str
    via: str
    ok: bool
    ms: int
    attempts: int


@dataclass
class ServerStats:
    requests: int = 0
    ok: int = 0
    failed: int = 0
    active: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    recent: Deque[RequestLog] = field(default_factory=lambda: deque(maxlen=10))
    started: float = field(default_factory=time.perf_counter)


class RotatingServer:
    def __init__(self, pool: ProxyPool, host: str = "127.0.0.1", port: int = 8899, timeout: float = 10.0,
                 password: str = ""):
        self.pool = pool
        self.password = password  # empty = no authentication (fine on 127.0.0.1)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.stats = ServerStats()
        self.revived = 0  # proxies that passed the recheck after being disabled
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port, limit=HEAD_LIMIT)
        self.port = self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        peer = writer.get_extra_info("peername") or ("?", 0)
        client = f"{peer[0]}:{peer[1]}"
        self.stats.active += 1
        try:
            try:
                # SOCKS5 and HTTP on the same port: SOCKS5 always starts with 0x05, HTTP with a letter
                first = await asyncio.wait_for(reader.readexactly(1), self.timeout)
                if first == SOCKS5_VERSION:
                    await self._serve_socks5(reader, writer, client)
                    return
                head = first + await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self.timeout)
                if head.startswith(STATUS_PREFIX):
                    await self._serve_status(writer, head)
                    return
                method, host, port, path, headers = parse_request_head(head)
                if not password_ok(headers, self.password):
                    writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                                 b'Proxy-Authenticate: Basic realm="proxy-scraper"\r\n'
                                 b"Content-Length: 0\r\nConnection: close\r\n\r\n")
                    return
            except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError,
                    UnicodeDecodeError):
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            selection = selection_from_headers(headers)
            await self._serve_request(reader, writer, client, method, host, port, path, headers, selection)
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass  # client hung up (also in the middle of a request body)
        finally:
            self.stats.active -= 1
            writer.close()

    async def _serve_request(self, reader, writer, client, method, host, port, path, headers,
                             selection: Selection = ANY) -> None:
        self.stats.requests += 1
        started = time.perf_counter()
        if method == "CONNECT":
            served = await self._serve_tunnel(reader, writer, client, host, port, started, selection)
        else:
            served = await self._serve_http(reader, writer, client, method, host, port, path, headers, started,
                                            selection)
        if not served:
            self.stats.failed += 1

    async def _serve_tunnel(self, reader, writer, client, host, port, started, selection: Selection = ANY,
                            established: bytes = HTTP_ESTABLISHED, refuse=None) -> bool:
        """CONNECT: open a tunnel first, then "200" to the client – if none works, it gets a 502.

        After that a proxy only counts as successful once it answers. The client's first packet (for HTTPS
        the start of the TLS handshake) is buffered and goes to the next proxy unnoticed if needed.
        """
        tried: Set[str] = set()
        # CONNECT is almost always TLS (also on ports like 8443) – the first ClientHello should only go through
        # proxies that passed the HTTPS test; without any, pick() falls back to all of them
        opened = await self._open_next(tried, host, port, tls=True, tunnel=True, selection=selection)
        if opened is None:
            self._log(client, host, port, None, False, started, len(tried))
            await (refuse or self._bad_gateway)(writer)
            return False
        writer.write(established)
        await writer.drain()
        first_out = await self._first_client_chunk(reader)
        tls = first_out[:1] == TLS_HANDSHAKE

        while opened is not None:
            entry, up_reader, up_writer = opened
            first_in = await self._exchange(up_reader, up_writer, first_out)
            if first_in is not None:
                await self._relay(reader, writer, client, host, port, started, len(tried), entry,
                                  up_reader, up_writer, first_out, first_in)
                return True
            self._give_up(entry, up_writer)
            opened = await self._open_next(tried, host, port, tls=tls, tunnel=True, selection=selection)
        self._log(client, host, port, None, False, started, len(tried))
        return False  # after "200 Connection established" all that's left is to close the connection

    async def _serve_http(self, reader, writer, client, method, host, port, path, headers, started,
                          selection: Selection = ANY) -> bool:
        """Plain HTTP request. HTTP upstreams get it as a classic proxy request (without CONNECT),
        SOCKS upstreams in the form for the target server. Small bodies are buffered for a switch."""
        body, replayable = await self._read_body(reader, headers)
        tried: Set[str] = set()
        while True:
            opened = await self._open_next(tried, host, port, tls=False, tunnel=False, selection=selection)
            if opened is None:
                break
            entry, up_reader, up_writer = opened
            if entry.result.ptype == "http":
                head = with_proxy_auth(forward_request(method, path, host, port, headers),
                                       parse_endpoint(entry.result.proxy))
            else:
                head = origin_request(method, path, host, port, headers)
            first_out = head + body
            if not replayable:
                # large or streamed body: no switch possible – send the head, pass the rest through
                up_writer.write(first_out)
                await up_writer.drain()
                return await self._relay(reader, writer, client, host, port, started, len(tried), entry,
                                         up_reader, up_writer, first_out, b"", upload=request_body_length(headers))
            first_in = await self._exchange(up_reader, up_writer, first_out)
            if first_in is not None:
                await self._relay(reader, writer, client, host, port, started, len(tried), entry,
                                  up_reader, up_writer, first_out, first_in, upload=0)
                return True
            self._give_up(entry, up_writer)
        self._log(client, host, port, None, False, started, len(tried))
        await self._bad_gateway(writer)
        return False

    async def _open_next(self, tried: Set[str], host: str, port: int, tls: bool, tunnel: bool,
                         selection: Selection = ANY):
        """Open the next proxy from the pool (at most MAX_ATTEMPTS per request). None = none left.

        A proxy that is reachable but can't reach the target is only blamed once another proxy reaches it:
        if every attempt fails that way, the target is the problem and nobody in the pool gets disabled."""
        refused = []  # proxies that answered but couldn't open the connection to the target
        while len(tried) < MAX_ATTEMPTS:
            entry = self.pool.pick(tried, tls=tls, selection=selection, target=f"{host}:{port}")
            if entry is None:
                return None
            tried.add(entry.result.key)
            # count as busy while connecting already – otherwise concurrent requests would see the fastest
            # proxy as free (important for --rotate fastest); released in _give_up or at the end of _relay
            entry.active += 1
            try:
                up_reader, up_writer = await open_upstream(entry, host, port, self.timeout, tunnel=tunnel)
            except Unsupported:
                entry.active -= 1  # this type can't do this target – not a failure of the proxy
                continue
            except TargetError:
                entry.active -= 1
                refused.append(entry)
                continue
            except UpstreamError:
                entry.active -= 1
                self.pool.report(entry, False)
                continue
            for other in refused:  # the target is reachable after all – those proxies were the problem
                self.pool.report(other, False)
            return entry, up_reader, up_writer
        return None

    async def _exchange(self, up_reader, up_writer, first_out: bytes) -> Optional[bytes]:
        """Send the first packet, wait for the first response. None = this proxy is no good right now."""
        try:
            if first_out:
                up_writer.write(first_out)
                await up_writer.drain()
            first_in = await asyncio.wait_for(up_reader.read(65536), self.timeout)
            if first_in and first_out[:1] != TLS_HANDSHAKE:
                first_in = await self._screen_first_answer(up_reader, first_in)
        except (OSError, asyncio.TimeoutError):
            return None
        if not first_in or not plausible_answer(first_out, first_in):
            return None
        return first_in

    async def _screen_first_answer(self, up_reader, first_in: bytes) -> bytes:
        """Read up to the final status line (past 100 Continue and the like). b"" = the proxy wants a login."""
        screen = ResponseScreen()
        out, verdict = screen.feed(first_in)
        while verdict is None:
            more = await asyncio.wait_for(up_reader.read(65536), self.timeout)
            if not more:
                return b""  # hung up before a final response came – that's not a success
            data, verdict = screen.feed(more)
            out += data
        return b"" if verdict == "407" else out

    async def _relay(self, reader, writer, client, host, port, started, attempts, entry,
                     up_reader, up_writer, first_out: bytes, first_in: bytes, upload=None) -> bool:
        """Pass both directions through. Success only counts once the upstream has answered – for
        streamed bodies (first_in empty) that means once any data comes back at all.

        upload: for plain HTTP only the rest of this request's body may go up (a byte count or a ChunkedEnd).
        Whatever the client sends after it – a second keep-alive request with its Proxy-Authorization,
        for example – never reaches the free proxy. None = tunnel, everything goes through."""
        if first_in:
            self._account(client, host, port, entry, True, started, attempts)
        try:
            self.stats.bytes_up += len(first_out)
            self.stats.bytes_down += len(first_in)
            if first_in:
                writer.write(first_in)
                await writer.drain()
            _, received = await asyncio.gather(
                self._pipe(reader, up_writer, up=True) if upload is None
                else self._send_body(reader, up_writer, upload),
                # without a first response up front (streamed body) watch for a 407 from the proxy here
                self._pipe(up_reader, writer, up=False, reject_proxy_auth=not first_in),
            )
        finally:
            entry.active -= 1
            up_writer.close()
        if not first_in:
            self._account(client, host, port, entry, received > 0, started, attempts)
        return bool(first_in) or received > 0

    def _give_up(self, entry, up_writer) -> None:
        """This proxy didn't deliver: count it as a failure, close the connection, release the reservation."""
        entry.active -= 1
        self.pool.report(entry, False)
        up_writer.close()

    def _account(self, client, host, port, entry, ok: bool, started, attempts) -> None:
        self.pool.report(entry, ok)
        if ok:
            self.stats.ok += 1
        self._log(client, host, port, entry, ok, started, attempts)

    async def _read_body(self, reader, headers) -> Tuple[bytes, bool]:
        """Read the request body if it's small enough to buffer -> (body, repeatable?)."""
        values = {name.lower(): value for name, value in headers}
        if b"chunked" in values.get(b"transfer-encoding", b"").lower():
            return b"", False
        if b"100-continue" in values.get(b"expect", b"").lower():
            return b"", False  # the client only sends the body after "100 Continue" from the target
        length = values.get(b"content-length", b"0").strip()
        if not length.isdigit() or int(length) > MAX_REPLAY_BODY:
            return b"", False
        return (await reader.readexactly(int(length)) if int(length) else b""), True

    async def _first_client_chunk(self, reader) -> bytes:
        """The client's first packet in the tunnel (for HTTPS: TLS ClientHello). Empty if the server is
        supposed to talk first (e.g. SSH) – then we wait for the other side right away."""
        try:
            data = await asyncio.wait_for(reader.read(65536), FIRST_CHUNK_WAIT)
            if data[:1] == TLS_HANDSHAKE:
                data = await self._complete_tls_record(reader, data)
            return data
        except asyncio.TimeoutError:
            return b""

    async def _complete_tls_record(self, reader, data: bytes) -> bytes:
        """Collect the first TLS record completely – it can be spread over several TCP packets, and when
        switching proxies not just a fragment of the ClientHello should go out. If the rest is slow, what
        arrived so far goes out anyway – dropping it would break the handshake for good."""
        while True:
            # first the 5-byte header, then the length is known (at most one buffer full)
            needed = 5 if len(data) < 5 else min(5 + int.from_bytes(data[3:5], "big"), 65536)
            if len(data) >= needed:
                return data
            try:
                more = await asyncio.wait_for(reader.read(needed - len(data)), FIRST_CHUNK_WAIT)
            except asyncio.TimeoutError:
                return data
            if not more:
                return data
            data += more

    async def _bad_gateway(self, writer) -> None:
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\n"
                     b"Connection: close\r\n\r\nNo proxy from the pool answered.\n")
        await writer.drain()

    async def _send_body(self, reader, writer, body) -> int:
        """Pass exactly the rest of one request body upstream, then stop reading from the client."""
        total = 0
        with contextlib.suppress(ConnectionError, OSError, ValueError):
            while body:
                data = await reader.read(min(body, 65536) if isinstance(body, int) else 65536)
                if not data:
                    break
                if isinstance(body, int):
                    body -= len(data)
                else:
                    end = body.feed(data)
                    if end is not None:
                        data, body = data[:end], 0
                total += len(data)
                self.stats.bytes_up += len(data)
                writer.write(data)
                await writer.drain()
        return total

    async def _pipe(self, reader, writer, up: bool, reject_proxy_auth: bool = False) -> int:
        """Pass data through until one side stops; returns the number of bytes.

        reject_proxy_auth: if the final response is a 407 (also after 100 Continue), the client gets
        a 502 instead and -1 is returned (the proxy counts as failed)."""
        total = 0
        screen = ResponseScreen() if reject_proxy_auth else None
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    if screen:  # hung up before a final response came – a 502 for the client
                        await self._bad_gateway(writer)
                        return -1
                    break
                if screen:
                    data, verdict = screen.feed(data)
                    if verdict == "407":
                        await self._bad_gateway(writer)
                        return -1
                    if verdict == "ok":
                        screen = None
                    if not data:
                        continue
                total += len(data)
                if up:
                    self.stats.bytes_up += len(data)
                else:
                    self.stats.bytes_down += len(data)
                writer.write(data)
                await writer.drain()
        except (ConnectionError, OSError, asyncio.TimeoutError):
            # one side hung up – that normally ends the relay just fine. But if no final response came yet
            # (the upstream aborts with an RST, for example, because our body sat unread in its buffer),
            # that's just as much a failure as a clean hang-up.
            if screen:
                with contextlib.suppress(ConnectionError, OSError):
                    await self._bad_gateway(writer)
                return -1
        finally:
            try:
                writer.write_eof()
            except (OSError, RuntimeError, AttributeError):
                writer.close()
        return total

    def _log(self, client, host, port, entry, ok, started, attempts) -> None:
        via = f"{entry.result.ptype}://{entry.result.proxy}" if entry else "–"
        target = host if port in (80, 443) else f"{host}:{port}"
        self.stats.recent.append(RequestLog(client, target, via, ok, round((time.perf_counter() - started) * 1000),
                                            attempts))

    # ------------------------------------------------------------------ SOCKS5, status, refreshing

    async def _serve_socks5(self, reader, writer, client) -> None:
        """SOCKS5 on the same port. Authentication optional – the user name carries the same wishes as with
        HTTP ("country-de-session-abc"). After that everything works like CONNECT, including switching on errors."""
        try:
            host, port, username = await asyncio.wait_for(socks5_accept(reader, writer, self.password), self.timeout)
        except (Socks5Refused, asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError, UnicodeError):
            return  # refused, hung up half-way, too slow or a broken address – close the connection
        self.stats.requests += 1
        started = time.perf_counter()

        async def refuse(w) -> None:
            w.write(socks5_reply(0x04))  # host unreachable – none of the proxies got through
            await w.drain()

        served = await self._serve_tunnel(reader, writer, client, host, port, started,
                                          Selection.from_username(username), socks5_reply(0x00), refuse)
        if not served:
            self.stats.failed += 1

    async def _serve_status(self, writer, head: bytes) -> None:
        target = head.split(b" ", 2)[1].split(b"?", 1)[0]
        kind = b"application/json"
        headers = [tuple(part.strip() for part in line.split(b":", 1)) for line in head.split(b"\r\n")[1:]
                   if b":" in line]
        if not password_ok(headers, self.password, b"authorization"):
            writer.write(b"HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Basic realm=\"proxy-scraper\"\r\n"
                         b"Content-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return
        if target == STATUS_PATH:
            status, body = b"200 OK", status_json(self).encode()
        elif target == METRICS_PATH:
            status, body, kind = b"200 OK", metrics_text(self).encode(), METRICS_TYPE
        else:  # only exactly these paths – typos shouldn't silently return the status
            status, body = b"404 Not Found", b'{"error": "unknown path, try /__proxy-scraper/status or /metrics"}'
        writer.write(b"HTTP/1.1 " + status + b"\r\nContent-Type: " + kind + b"\r\nCache-Control: no-store\r\n"
                     b"Content-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
        await writer.drain()

    async def keep_fresh(self, recheck, interval: float = 300.0) -> None:
        """Recheck disabled proxies regularly and bring them back when they work again.

        `recheck(result)` is the normal check (True = works). Runs until the task is cancelled."""
        while True:
            await asyncio.sleep(interval)
            await self.refresh_once(recheck)

    async def refresh_once(self, recheck) -> int:
        dead = [e for e in self.pool.entries if e.disabled]
        if not dead:
            return 0
        results = await asyncio.gather(*(recheck(e.result) for e in dead), return_exceptions=True)
        revived = 0
        for entry, ok in zip(dead, results):
            if ok is True:
                self.pool.revive(entry)
                revived += 1
        self.revived += revived
        return revived
