"""Lokaler rotierender Proxy-Server (--serve).

Nimmt HTTP-Proxy-Anfragen an (CONNECT für HTTPS und normale HTTP-Anfragen) und schickt jede
Verbindung über einen der gefundenen Proxys. Schnelle, zuverlässige Proxys werden bevorzugt;
scheitert einer, wird automatisch der nächste versucht, und wer mehrmals hintereinander scheitert,
fliegt aus der Rotation.
"""

from __future__ import annotations

import asyncio
import random
import re
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Set, Tuple

from .checker import CheckResult
from .handshake import parse_endpoint, socks4, socks5, socks5_domain, stream_io, with_proxy_auth

MAX_ATTEMPTS = 3            # so viele Proxys pro Anfrage, bevor der Client einen Fehler bekommt
FIRST_CHUNK_WAIT = 5.0      # so lange auf das erste Paket des Clients im Tunnel warten
MAX_REPLAY_BODY = 1024 * 1024  # Request-Bodies bis zu dieser Größe werden für einen Proxy-Wechsel gepuffert
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
        return "CONNECT", host.strip("[]"), _valid_port(port), b"", headers
    if not target.lower().startswith(b"http://"):
        raise ValueError("nur absolute http://-URLs oder CONNECT")
    rest = target[7:]
    hostport, slash, path = rest.partition(b"/")
    host, _, port = hostport.decode("ascii").partition(":")
    return method.decode("ascii"), host, _valid_port(port or "80"), b"/" + path if slash else b"/", headers


def _valid_port(text: str) -> int:
    port = int(text)
    if not 0 < port < 65536:
        raise ValueError(f"ungültiger Port {port}")
    return port


def origin_request(method: str, path: bytes, host: str, port: int, headers: List[Tuple[bytes, bytes]]) -> bytes:
    """Anfrage für den Zielserver: Pfad statt absoluter URL, ohne Proxy-Header, eine Anfrage pro Verbindung."""
    lines = [f"{method} ".encode() + path + b" HTTP/1.1"]
    if not any(name.lower() == b"host" for name, _ in headers):
        lines.append(b"Host: " + (host if port == 80 else f"{host}:{port}").encode())
    lines += [name + b": " + value for name, value in headers if name.lower() not in HOP_BY_HOP]
    lines.append(b"Connection: close")
    return b"\r\n".join(lines) + b"\r\n\r\n"


def forward_request(method: str, path: bytes, host: str, port: int, headers: List[Tuple[bytes, bytes]]) -> bytes:
    """Anfrage an einen HTTP-Upstream-Proxy: absolute URL wie vom Client, nur ohne Proxy-Header."""
    authority = host if port == 80 else f"{host}:{port}"
    request = origin_request(method, path, host, port, headers)
    first_line, rest = request.split(b"\r\n", 1)
    return f"{method} http://{authority}".encode() + path + b" HTTP/1.1\r\n" + rest


async def open_upstream(entry: PoolEntry, host: str, port: int, timeout: float, tunnel: bool = True):
    """Verbindung über den Proxy zu host:port. tunnel=False heißt: HTTP-Upstream im Weiterleitungsmodus
    (klassische Proxy-Anfrage ohne CONNECT). Wirft UpstreamError, wenn der Proxy nicht mitspielt."""
    r = entry.result
    ep = parse_endpoint(r.proxy)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ep.host, ep.port), timeout)
    except (OSError, asyncio.TimeoutError) as e:
        raise UpstreamError(f"Proxy nicht erreichbar: {e!r}") from None
    if r.ptype == "http" and not tunnel:
        return reader, writer
    try:
        await asyncio.wait_for(_handshake(r.ptype, r.proxy, reader, writer, host, port), timeout)
    except BaseException as e:
        writer.close()
        if isinstance(e, (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, UpstreamError, ValueError)):
            raise UpstreamError(f"Tunnel abgelehnt: {e!r}") from None
        raise
    return reader, writer


async def _handshake(ptype: str, proxy: str, reader, writer, host: str, port: int) -> None:
    ep = parse_endpoint(proxy)
    if ptype == "http":
        connect = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode()
        writer.write(with_proxy_auth(connect, ep))
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        first = head.split(b"\r\n", 1)[0]
        parts = first.split()
        # exakt 200 – "HTTP/1.1 2000" o. ä. ist kein aufgebauter Tunnel
        if len(parts) < 2 or not parts[0].startswith(b"HTTP/") or parts[1] != b"200":
            raise UpstreamError(first.decode("latin-1"))
    elif ptype == "socks4":
        ip = await _resolve(host, port)  # SOCKS4 kennt nur IPv4-Adressen
        if not await socks4(*stream_io(reader, writer), ep, socket.inet_aton(ip), port):
            raise UpstreamError("SOCKS4 abgelehnt")
    else:
        # Hostname statt IP: die Namensauflösung passiert beim Proxy (kein DNS-Leck)
        if not await socks5(*stream_io(reader, writer), ep, socks5_domain(host), port):
            raise UpstreamError("SOCKS5 abgelehnt")


PROXY_AUTH_REQUIRED = re.compile(rb"HTTP/1\.[01] 407\b")
STATUS_LEN = len(b"HTTP/1.1 407 ")
STATUS_RE = re.compile(rb"HTTP/1\.[01] (\d{3})[ \r\n]")  # genau drei Ziffern – "4070" ist kein 407
SCREEN_LIMIT = 16384


class ResponseScreen:
    """Prüft den Anfang einer Upstream-Antwort, bis die endgültige Statuszeile da ist.

    Zwischenantworten (100 Continue & Co.) gehen sofort an den Client weiter; kommt danach ein 407,
    soll der Client das nie sehen. feed() gibt zurück, was schon weiter darf, und die Entscheidung:
    None = noch offen, "ok" = alles Weitere einfach durchreichen, "407" = Proxy will einen Login
    (oder schickt eine unplausibel lange Zwischenantwort – beides heißt: diesen Upstream nicht nehmen)."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes):
        self.buf += data
        out = b""
        while True:
            head = self.buf
            if len(head) < STATUS_LEN and b"\n" not in head and head[:5] == b"HTTP/"[:len(head[:5])]:
                return out, None  # Statuszeile noch unvollständig
            m = STATUS_RE.match(head)
            if not m:
                return out + self._flush(), "ok"  # keine HTTP-Antwort (z. B. Tunnel) – nichts zu prüfen
            code = m.group(1)
            if code == b"407":
                return out, "407"
            if not code.startswith(b"1") or code == b"101":  # 101 Switching Protocols ist endgültig
                return out + self._flush(), "ok"
            end = head.find(b"\r\n\r\n")
            if end < 0:
                if len(head) > SCREEN_LIMIT:
                    return out, "407"  # riesige Zwischenantwort – lieber als gescheitert werten als blind durchlassen
                return out, None  # Zwischenantwort noch nicht vollständig
            out += head[:end + 4]
            self.buf = head[end + 4:]
            if not self.buf:
                return out, None

    def _flush(self) -> bytes:
        data, self.buf = self.buf, b""
        return data


def plausible_answer(first_out: bytes, first_in: bytes) -> bool:
    """Passt die erste Antwort zur Anfrage? Beginnt der Client mit einem TLS-Handshake (0x16), muss die
    Gegenseite auch TLS sprechen – manche Proxys schicken im Tunnel stattdessen eine HTTP-Fehlerseite.
    Ein 407 kommt immer vom Proxy selbst (Login fehlt oder falsch), nie von der Zielseite."""
    if first_out[:1] == TLS_HANDSHAKE:
        return first_in[:1] in (TLS_HANDSHAKE, TLS_ALERT)
    return not PROXY_AUTH_REQUIRED.match(first_in)


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
        self.stats.requests += 1
        started = time.perf_counter()
        if method == "CONNECT":
            served = await self._serve_tunnel(reader, writer, client, host, port, started)
        else:
            served = await self._serve_http(reader, writer, client, method, host, port, path, headers, started)
        if not served:
            self.stats.failed += 1

    async def _serve_tunnel(self, reader, writer, client, host, port, started) -> bool:
        """CONNECT: erst einen Tunnel aufbauen, dann "200" an den Client – klappt keiner, gibt es 502.

        Danach zählt ein Proxy erst als erfolgreich, wenn er antwortet. Das erste Client-Paket (bei HTTPS
        der Beginn des TLS-Handshakes) ist gepuffert und geht bei Bedarf unbemerkt an den nächsten Proxy.
        """
        tried: Set[str] = set()
        # CONNECT ist fast immer TLS (auch auf Ports wie 8443) – das erste ClientHello soll nur über Proxys
        # gehen, die den HTTPS-Test bestanden haben; ohne solche greift pick() auf alle zurück
        opened = await self._open_next(tried, host, port, tls=True, tunnel=True)
        if opened is None:
            self._log(client, host, port, None, False, started, len(tried))
            await self._bad_gateway(writer)
            return False
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
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
            self.pool.report(entry, False)
            up_writer.close()
            opened = await self._open_next(tried, host, port, tls=tls, tunnel=True)
        self._log(client, host, port, None, False, started, len(tried))
        return False  # nach "200 Connection established" bleibt nur, die Verbindung zu schließen

    async def _serve_http(self, reader, writer, client, method, host, port, path, headers, started) -> bool:
        """Normale HTTP-Anfrage. HTTP-Upstreams bekommen sie als klassische Proxy-Anfrage (ohne CONNECT),
        SOCKS-Upstreams in der Form für den Zielserver. Kleine Bodies werden für einen Wechsel gepuffert."""
        body, replayable = await self._read_body(reader, headers)
        tried: Set[str] = set()
        while True:
            opened = await self._open_next(tried, host, port, tls=False, tunnel=False)
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
                # Großer oder gestreamter Body: kein Wechsel möglich – Kopf senden, den Rest durchreichen
                up_writer.write(first_out)
                await up_writer.drain()
                return await self._relay(reader, writer, client, host, port, started, len(tried), entry,
                                         up_reader, up_writer, first_out, b"")
            first_in = await self._exchange(up_reader, up_writer, first_out)
            if first_in is not None:
                await self._relay(reader, writer, client, host, port, started, len(tried), entry,
                                  up_reader, up_writer, first_out, first_in)
                return True
            self.pool.report(entry, False)
            up_writer.close()
        self._log(client, host, port, None, False, started, len(tried))
        await self._bad_gateway(writer)
        return False

    async def _open_next(self, tried: Set[str], host: str, port: int, tls: bool, tunnel: bool):
        """Nächsten Proxy aus dem Pool öffnen (höchstens MAX_ATTEMPTS pro Anfrage). None = keiner mehr."""
        while len(tried) < MAX_ATTEMPTS:
            entry = self.pool.pick(tried, tls=tls)
            if entry is None:
                return None
            tried.add(entry.result.key)
            try:
                up_reader, up_writer = await open_upstream(entry, host, port, self.timeout, tunnel=tunnel)
            except UpstreamError:
                self.pool.report(entry, False)
                continue
            return entry, up_reader, up_writer
        return None

    async def _exchange(self, up_reader, up_writer, first_out: bytes) -> Optional[bytes]:
        """Erstes Paket senden, erste Antwort abwarten. None = dieser Proxy taugt gerade nicht."""
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
        """Bis zur endgültigen Statuszeile lesen (über 100 Continue & Co. hinweg). b"" = Proxy will Login."""
        screen = ResponseScreen()
        out, verdict = screen.feed(first_in)
        while verdict is None:
            more = await asyncio.wait_for(up_reader.read(65536), self.timeout)
            if not more:
                return b""  # aufgelegt, bevor eine endgültige Antwort kam – das ist kein Erfolg
            data, verdict = screen.feed(more)
            out += data
        return b"" if verdict == "407" else out

    async def _relay(self, reader, writer, client, host, port, started, attempts, entry,
                     up_reader, up_writer, first_out: bytes, first_in: bytes) -> bool:
        """Beide Richtungen durchreichen. Erfolg zählt erst, wenn der Upstream geantwortet hat – bei
        gestreamten Bodies (first_in leer) also erst, wenn überhaupt Daten zurückkommen."""
        if first_in:
            self._account(client, host, port, entry, True, started, attempts)
        entry.active += 1
        try:
            self.stats.bytes_up += len(first_out)
            self.stats.bytes_down += len(first_in)
            if first_in:
                writer.write(first_in)
                await writer.drain()
            _, received = await asyncio.gather(
                self._pipe(reader, up_writer, up=True),
                # ohne erste Antwort vorab (gestreamter Body) hier auf ein 407 des Proxys achten
                self._pipe(up_reader, writer, up=False, reject_proxy_auth=not first_in),
            )
        finally:
            entry.active -= 1
            up_writer.close()
        if not first_in:
            self._account(client, host, port, entry, received > 0, started, attempts)
        return bool(first_in) or received > 0

    def _account(self, client, host, port, entry, ok: bool, started, attempts) -> None:
        self.pool.report(entry, ok)
        if ok:
            self.stats.ok += 1
        self._log(client, host, port, entry, ok, started, attempts)

    async def _read_body(self, reader, headers) -> Tuple[bytes, bool]:
        """Request-Body lesen, wenn er klein genug zum Puffern ist -> (Body, wiederholbar?)."""
        values = {name.lower(): value for name, value in headers}
        if b"chunked" in values.get(b"transfer-encoding", b"").lower():
            return b"", False
        if b"100-continue" in values.get(b"expect", b"").lower():
            return b"", False  # der Client schickt den Body erst nach "100 Continue" vom Ziel
        length = values.get(b"content-length", b"0").strip()
        if not length.isdigit() or int(length) > MAX_REPLAY_BODY:
            return b"", False
        return (await reader.readexactly(int(length)) if int(length) else b""), True

    async def _first_client_chunk(self, reader) -> bytes:
        """Erstes Paket des Clients im Tunnel (bei HTTPS: TLS ClientHello). Leer, falls der Server zuerst
        sprechen soll (z. B. SSH) – dann wird direkt auf die Gegenseite gewartet."""
        try:
            data = await asyncio.wait_for(reader.read(65536), FIRST_CHUNK_WAIT)
            if data[:1] == TLS_HANDSHAKE:
                data = await self._complete_tls_record(reader, data)
            return data
        except asyncio.TimeoutError:
            return b""

    async def _complete_tls_record(self, reader, data: bytes) -> bytes:
        """Ersten TLS-Record vollständig sammeln – er kann über mehrere TCP-Pakete verteilt sein, und bei
        einem Proxy-Wechsel soll nicht nur ein Bruchstück des ClientHello weitergehen."""
        while True:
            # erst den 5-Byte-Kopf, dann steht die Länge fest (höchstens ein Puffer voll)
            needed = 5 if len(data) < 5 else min(5 + int.from_bytes(data[3:5], "big"), 65536)
            if len(data) >= needed:
                return data
            more = await asyncio.wait_for(reader.read(needed - len(data)), FIRST_CHUNK_WAIT)
            if not more:
                return data
            data += more

    async def _bad_gateway(self, writer) -> None:
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\n"
                     b"Connection: close\r\n\r\nKein Proxy aus dem Pool hat geantwortet.\n")
        await writer.drain()

    async def _pipe(self, reader, writer, up: bool, reject_proxy_auth: bool = False) -> int:
        """Daten weiterreichen, bis eine Seite aufhört; gibt die Anzahl der Bytes zurück.

        reject_proxy_auth: ist die endgültige Antwort ein 407 (auch nach 100 Continue), bekommt der
        Client stattdessen 502 und es wird -1 zurückgegeben (Proxy gilt als gescheitert)."""
        total = 0
        screen = ResponseScreen() if reject_proxy_auth else None
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    if screen:  # aufgelegt, bevor eine endgültige Antwort kam – für den Client ein 502
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
            # eine Seite hat aufgelegt – das beendet die Weiterleitung normalerweise ganz normal. Kam aber noch
            # keine endgültige Antwort (Upstream bricht z. B. per RST ab, weil unser Body ungelesen im Puffer
            # lag), ist das genauso ein Fehlschlag wie ein sauberes Auflegen.
            if screen:
                try:
                    await self._bad_gateway(writer)
                except (ConnectionError, OSError):
                    pass
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
