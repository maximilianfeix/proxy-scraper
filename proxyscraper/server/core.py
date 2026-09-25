"""Lokaler rotierender Proxy-Server (--serve).

Nimmt HTTP-Proxy-Anfragen an (CONNECT für HTTPS und normale HTTP-Anfragen) und schickt jede
Verbindung über einen der gefundenen Proxys. Schnelle, zuverlässige Proxys werden bevorzugt;
scheitert einer, wird automatisch der nächste versucht, und wer mehrmals hintereinander scheitert,
fliegt aus der Rotation.
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
)
from .pool import ANY, ProxyPool, Selection
from .socks import SOCKS5_VERSION, Socks5Refused, socks5_accept, socks5_reply
from .status import STATUS_PREFIX, selection_from_headers, status_json
from .upstream import UpstreamError, open_upstream

MAX_ATTEMPTS = 3            # so viele Proxys pro Anfrage, bevor der Client einen Fehler bekommt
FIRST_CHUNK_WAIT = 5.0      # so lange auf das erste Paket des Clients im Tunnel warten
MAX_REPLAY_BODY = 1024 * 1024  # Request-Bodies bis zu dieser Größe werden für einen Proxy-Wechsel gepuffert
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
    def __init__(self, pool: ProxyPool, host: str = "127.0.0.1", port: int = 8899, timeout: float = 10.0):
        self.pool = pool
        self.host = host
        self.port = port
        self.timeout = timeout
        self.stats = ServerStats()
        self.revived = 0  # Proxys, die nach dem Ausmustern die Nachprüfung bestanden haben
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
                # SOCKS5 und HTTP auf demselben Port: SOCKS5 beginnt immer mit 0x05, HTTP mit einem Buchstaben
                first = await asyncio.wait_for(reader.readexactly(1), self.timeout)
                if first == SOCKS5_VERSION:
                    await self._serve_socks5(reader, writer, client)
                    return
                head = first + await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self.timeout)
                if head.startswith(STATUS_PREFIX):
                    await self._serve_status(writer)
                    return
                method, host, port, path, headers = parse_request_head(head)
            except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError,
                    UnicodeDecodeError):
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            selection = selection_from_headers(headers)
            await self._serve_request(reader, writer, client, method, host, port, path, headers, selection)
        except (ConnectionError, OSError):
            pass  # Client hat aufgelegt
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
        """CONNECT: erst einen Tunnel aufbauen, dann "200" an den Client – klappt keiner, gibt es 502.

        Danach zählt ein Proxy erst als erfolgreich, wenn er antwortet. Das erste Client-Paket (bei HTTPS
        der Beginn des TLS-Handshakes) ist gepuffert und geht bei Bedarf unbemerkt an den nächsten Proxy.
        """
        tried: Set[str] = set()
        # CONNECT ist fast immer TLS (auch auf Ports wie 8443) – das erste ClientHello soll nur über Proxys
        # gehen, die den HTTPS-Test bestanden haben; ohne solche greift pick() auf alle zurück
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
            self.pool.report(entry, False)
            up_writer.close()
            opened = await self._open_next(tried, host, port, tls=tls, tunnel=True, selection=selection)
        self._log(client, host, port, None, False, started, len(tried))
        return False  # nach "200 Connection established" bleibt nur, die Verbindung zu schließen

    async def _serve_http(self, reader, writer, client, method, host, port, path, headers, started,
                          selection: Selection = ANY) -> bool:
        """Normale HTTP-Anfrage. HTTP-Upstreams bekommen sie als klassische Proxy-Anfrage (ohne CONNECT),
        SOCKS-Upstreams in der Form für den Zielserver. Kleine Bodies werden für einen Wechsel gepuffert."""
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

    async def _open_next(self, tried: Set[str], host: str, port: int, tls: bool, tunnel: bool,
                         selection: Selection = ANY):
        """Nächsten Proxy aus dem Pool öffnen (höchstens MAX_ATTEMPTS pro Anfrage). None = keiner mehr."""
        while len(tried) < MAX_ATTEMPTS:
            entry = self.pool.pick(tried, tls=tls, selection=selection, target=f"{host}:{port}")
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

    # ------------------------------------------------------------------ SOCKS5, Status, Auffrischen

    async def _serve_socks5(self, reader, writer, client) -> None:
        """SOCKS5 auf demselben Port. Anmeldung optional – der Benutzername trägt dieselben Wünsche wie bei
        HTTP ("country-de-session-abc"). Danach läuft alles wie bei CONNECT, inklusive Wechsel bei Fehlern."""
        try:
            host, port, username = await asyncio.wait_for(socks5_accept(reader, writer), self.timeout)
        except Socks5Refused:
            return
        self.stats.requests += 1
        started = time.perf_counter()

        async def refuse(w) -> None:
            w.write(socks5_reply(0x04))  # Host unreachable – keiner der Proxys kam durch
            await w.drain()

        served = await self._serve_tunnel(reader, writer, client, host, port, started,
                                          Selection.from_username(username), socks5_reply(0x00), refuse)
        if not served:
            self.stats.failed += 1

    async def _serve_status(self, writer) -> None:
        body = status_json(self).encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n"
                     b"Content-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
        await writer.drain()

    async def keep_fresh(self, recheck, interval: float = 300.0) -> None:
        """Ausgemusterte Proxys regelmäßig nachprüfen und zurückholen, wenn sie wieder funktionieren.

        `recheck(result)` ist die normale Prüfung (True = funktioniert). Läuft, bis der Task abgebrochen wird."""
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
