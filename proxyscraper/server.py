"""Lokaler rotierender Proxy-Server (--serve).

Nimmt HTTP-Proxy-Anfragen an (CONNECT für HTTPS und normale HTTP-Anfragen) und schickt jede
Verbindung über einen der gefundenen Proxys. Schnelle, zuverlässige Proxys werden bevorzugt;
scheitert einer, wird automatisch der nächste versucht, und wer mehrmals hintereinander scheitert,
fliegt aus der Rotation.
"""

from __future__ import annotations

import asyncio
import random
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Set, Tuple

from .checker import CheckResult, _socks5_reply_ok

MAX_ATTEMPTS = 3            # so viele Proxys pro Anfrage, bevor der Client einen Fehler bekommt
FIRST_CHUNK_WAIT = 5.0      # so lange auf das erste Paket des Clients im Tunnel warten
DISABLE_AFTER = 3           # so viele Fehlschläge hintereinander -> aus der Rotation
HEAD_LIMIT = 64 * 1024
TLS_HANDSHAKE, TLS_ALERT = b"\x16", b"\x15"  # erstes Byte eines TLS-Records
HOP_BY_HOP = {b"proxy-connection", b"connection", b"keep-alive", b"proxy-authorization", b"te", b"upgrade"}


class UpstreamError(Exception):
    """Der gewählte Proxy hat die Verbindung nicht aufgebaut – nächster Versuch."""


@dataclass
class PoolEntry:
    result: CheckResult
    ok: int = 0
    fail: int = 0
    fail_streak: int = 0
    active: int = 0
    disabled: bool = False

    @property
    def weight(self) -> float:
        # Schnell und bewährt bevorzugen, aber allen eine Chance geben
        reliability = (self.ok + 1) / (self.ok + self.fail + 2)
        return reliability / (self.result.latency + 300)


class ProxyPool:
    def __init__(self, results: List[CheckResult], rng: Optional[random.Random] = None):
        self.entries = [PoolEntry(r) for r in sorted(results, key=lambda r: r.latency)]
        self.rng = rng or random.Random()

    @property
    def usable(self) -> List[PoolEntry]:
        return [e for e in self.entries if not e.disabled]

    @property
    def tls_capable(self) -> List[PoolEntry]:
        return [e for e in self.usable if e.result.https]

    def pick(self, exclude: Set[str], tls: bool = False) -> Optional[PoolEntry]:
        """Gewichtete Zufallswahl. Für TLS nur Proxys, die den HTTPS-Test (verifiziertes TLS) bestanden
        haben – andere brechen die Verschlüsselung oft auf. Gibt es keine, dann alle."""
        candidates = [e for e in self.usable if e.result.key not in exclude]
        if tls and any(e.result.https for e in self.usable):
            candidates = [e for e in candidates if e.result.https]
        if not candidates:
            return None
        return self.rng.choices(candidates, weights=[e.weight for e in candidates])[0]

    def report(self, entry: PoolEntry, ok: bool) -> None:
        if ok:
            entry.ok += 1
            entry.fail_streak = 0
        else:
            entry.fail += 1
            entry.fail_streak += 1
            if entry.fail_streak >= DISABLE_AFTER:
                entry.disabled = True


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


def parse_request_head(head: bytes) -> Tuple[str, str, int, bytes, List[Tuple[bytes, bytes]]]:
    """-> (Methode, Host, Port, Pfad, Header). Unterstützt CONNECT host:port und absolute URLs."""
    lines = head.split(b"\r\n")
    method, target, version = lines[0].split(b" ", 2)
    headers = []
    for line in lines[1:]:
        if line:
            name, _, value = line.partition(b":")
            headers.append((name.strip(), value.strip()))
    if method == b"CONNECT":
        host, _, port = target.decode("ascii").rpartition(":")
        return "CONNECT", host.strip("[]"), int(port), b"", headers
    if not target.lower().startswith(b"http://"):
        raise ValueError("nur absolute http://-URLs oder CONNECT")
    rest = target[7:]
    hostport, slash, path = rest.partition(b"/")
    host, _, port = hostport.decode("ascii").partition(":")
    return method.decode("ascii"), host, int(port or 80), b"/" + path if slash else b"/", headers


def origin_request(method: str, path: bytes, host: str, port: int, headers: List[Tuple[bytes, bytes]]) -> bytes:
    """Anfrage für den Zielserver: Pfad statt absoluter URL, ohne Proxy-Header, eine Anfrage pro Verbindung."""
    lines = [f"{method} ".encode() + path + b" HTTP/1.1"]
    if not any(name.lower() == b"host" for name, _ in headers):
        lines.append(b"Host: " + (host if port == 80 else f"{host}:{port}").encode())
    lines += [name + b": " + value for name, value in headers if name.lower() not in HOP_BY_HOP]
    lines.append(b"Connection: close")
    return b"\r\n".join(lines) + b"\r\n\r\n"


async def open_upstream(entry: PoolEntry, host: str, port: int, timeout: float):
    """Tunnel über den Proxy zu host:port. Wirft UpstreamError, wenn der Proxy nicht mitspielt."""
    r = entry.result
    proxy_host, proxy_port = r.proxy.rsplit(":", 1)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(proxy_host, int(proxy_port)), timeout)
    except (OSError, asyncio.TimeoutError) as e:
        raise UpstreamError(f"Proxy nicht erreichbar: {e!r}") from None
    try:
        await asyncio.wait_for(_handshake(r.ptype, reader, writer, host, port), timeout)
    except BaseException as e:
        writer.close()
        if isinstance(e, (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, UpstreamError, ValueError)):
            raise UpstreamError(f"Tunnel abgelehnt: {e!r}") from None
        raise
    return reader, writer


async def _handshake(ptype: str, reader, writer, host: str, port: int) -> None:
    if ptype == "http":
        writer.write(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        first = head.split(b"\r\n", 1)[0]
        if not (first.startswith(b"HTTP/") and b" 200" in first):
            raise UpstreamError(first.decode("latin-1"))
    elif ptype == "socks4":
        ip = await _resolve(host, port)  # SOCKS4 kennt nur IPv4-Adressen
        writer.write(b"\x04\x01" + port.to_bytes(2, "big") + socket.inet_aton(ip) + b"\x00")
        await writer.drain()
        if (await reader.readexactly(8))[1] != 0x5A:
            raise UpstreamError("SOCKS4 abgelehnt")
    else:
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        if await reader.readexactly(2) != b"\x05\x00":
            raise UpstreamError("SOCKS5-Anmeldung abgelehnt")
        name = host.encode("idna")
        # Hostname statt IP: die Namensauflösung passiert beim Proxy (kein DNS-Leck)
        writer.write(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + port.to_bytes(2, "big"))
        await writer.drain()
        if not await _socks5_reply_ok(reader.readexactly):
            raise UpstreamError("SOCKS5-Verbindung abgelehnt")


def plausible_answer(first_out: bytes, first_in: bytes) -> bool:
    """Passt die erste Antwort zur Anfrage? Beginnt der Client mit einem TLS-Handshake (0x16), muss die
    Gegenseite auch TLS sprechen – manche Proxys schicken im Tunnel stattdessen eine HTTP-Fehlerseite."""
    if first_out[:1] == TLS_HANDSHAKE:
        return first_in[:1] in (TLS_HANDSHAKE, TLS_ALERT)
    return True


async def _resolve(host: str, port: int) -> str:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, family=socket.AF_INET)
    return infos[0][4][0]


class RotatingServer:
    def __init__(self, pool: ProxyPool, host: str = "127.0.0.1", port: int = 8899, timeout: float = 10.0):
        self.pool = pool
        self.host = host
        self.port = port
        self.timeout = timeout
        self.stats = ServerStats()
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
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self.timeout)
                method, host, port, path, headers = parse_request_head(head)
            except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError,
                    UnicodeDecodeError):
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            await self._serve_request(reader, writer, client, method, host, port, path, headers)
        except (ConnectionError, OSError):
            pass  # Client hat aufgelegt
        finally:
            self.stats.active -= 1
            writer.close()

    async def _serve_request(self, reader, writer, client, method, host, port, path, headers) -> None:
        """Proxy wählen, erstes Paket senden, auf Antwort warten – sonst mit demselben Paket zum nächsten.

        Erst eine Antwort zählt als Erfolg: Manche Proxys nehmen CONNECT an und liefern dann nichts.
        Weil das erste Paket gepuffert ist (bei HTTPS der Beginn des TLS-Handshakes), merkt der Client
        vom Wechsel nichts.
        """
        self.stats.requests += 1
        started = time.perf_counter()
        if method == "CONNECT":
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            first_out = await self._first_client_chunk(reader)
        else:
            first_out = origin_request(method, path, host, port, headers)

        tried: Set[str] = set()
        tls = first_out[:1] == TLS_HANDSHAKE
        for attempt in range(1, MAX_ATTEMPTS + 1):
            entry = self.pool.pick(tried, tls=tls)
            if entry is None:
                break
            tried.add(entry.result.key)
            opened = await self._try_upstream(entry, host, port, first_out)
            if opened is None:
                self.pool.report(entry, False)
                continue
            up_reader, up_writer, first_in = opened
            self.pool.report(entry, True)
            self.stats.ok += 1
            self._log(client, host, port, entry, True, started, attempt)
            entry.active += 1
            try:
                self.stats.bytes_up += len(first_out)
                self.stats.bytes_down += len(first_in)
                writer.write(first_in)
                await writer.drain()
                await asyncio.gather(
                    self._pipe(reader, up_writer, up=True),
                    self._pipe(up_reader, writer, up=False),
                )
            finally:
                entry.active -= 1
                up_writer.close()
            return

        self.stats.failed += 1
        self._log(client, host, port, None, False, started, len(tried))
        if method != "CONNECT":  # nach "200 Connection established" bleibt nur, die Verbindung zu schließen
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\n"
                         b"Connection: close\r\n\r\nKein Proxy aus dem Pool hat geantwortet.\n")
            await writer.drain()

    async def _first_client_chunk(self, reader) -> bytes:
        """Erstes Paket des Clients im Tunnel (bei HTTPS: TLS ClientHello). Leer, falls der Server zuerst
        sprechen soll (z. B. SSH) – dann wird direkt auf die Gegenseite gewartet."""
        try:
            return await asyncio.wait_for(reader.read(65536), FIRST_CHUNK_WAIT)
        except asyncio.TimeoutError:
            return b""

    async def _try_upstream(self, entry: PoolEntry, host: str, port: int, first_out: bytes):
        """Tunnel aufbauen, erstes Paket senden, erste Antwort abwarten. None = dieser Proxy taugt gerade nicht."""
        try:
            up_reader, up_writer = await open_upstream(entry, host, port, self.timeout)
        except UpstreamError:
            return None
        try:
            if first_out:
                up_writer.write(first_out)
                await up_writer.drain()
            first_in = await asyncio.wait_for(up_reader.read(65536), self.timeout)
        except (OSError, asyncio.TimeoutError):
            first_in = b""
        if not first_in or not plausible_answer(first_out, first_in):
            up_writer.close()
            return None
        return up_reader, up_writer, first_in

    async def _pipe(self, reader, writer, up: bool) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                if up:
                    self.stats.bytes_up += len(data)
                else:
                    self.stats.bytes_down += len(data)
                writer.write(data)
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                writer.write_eof()
            except (OSError, RuntimeError, AttributeError):
                writer.close()

    def _log(self, client, host, port, entry, ok, started, attempts) -> None:
        via = f"{entry.result.ptype}://{entry.result.proxy}" if entry else "–"
        target = host if port in (80, 443) else f"{host}:{port}"
        self.stats.recent.append(RequestLog(client, target, via, ok, round((time.perf_counter() - started) * 1000),
                                            attempts))
