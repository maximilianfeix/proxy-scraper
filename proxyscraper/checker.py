"""Proxy-Prüfung mit eigenen Protokoll-Handshakes (HTTP, SOCKS4, SOCKS5).

Basisprüfung: eine TCP-Verbindung pro Proxy, Abruf der Exit-IP über checkip.amazonaws.com.
Bestätigung (nur für Proxys, die die Basisprüfung bestehen, also wenige):
  - zweite, unabhängige Anfrage an httpbin.org/get – sortiert Honeypots aus, die nur auf die
    Prüfanfrage mit "200 + IP" antworten und alles andere ablehnen. Dieselbe Antwort zeigt die
    ankommenden Header und damit die Anonymitätsstufe.
Detailprüfung:
  - HTTPS: Tunnel zu Port 443 aufbauen und darin eine verifizierte TLS-Verbindung – scheitert bei
    Proxys, die kein CONNECT können oder TLS aufbrechen (MITM).
"""

from __future__ import annotations

import asyncio
import errno
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
from .netio import USER_AGENT, dechunk, read_response, ssl_context
from .parsing import normalize_public_ip, split_key
from .targets import Target

# Prüfziel: liefert die IP zurück, die beim Server ankommt (nur Text, sehr klein).
# Bewusst NICHT hinter Cloudflare – sonst "funktionieren" beliebige Cloudflare-IPs als Fake-Proxy.
JUDGE_HOST = DEFAULT_JUDGE.host  # für die eigene IP; geprüft wird über Checker.judge
# Zweites, unabhängiges Prüfziel: liefert JSON mit Absender-IP ("origin") und empfangenen Headern
CONFIRM_HOST = "httpbin.org"
CONFIRM_PORT = 80
# Bewusst ohne Proxy-Connection-Header – der würde sonst selbst als Proxy-Spur auftauchen
_CONFIRM_HEADERS = f"Host: {CONFIRM_HOST}\r\nUser-Agent: {USER_AGENT}\r\nAccept: */*\r\nConnection: close\r\n\r\n"
CONFIRM_REQUEST = f"GET /get HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()
HTTP_PROXY_CONFIRM_REQUEST = f"GET http://{CONFIRM_HOST}/get HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()

CONTENT_LENGTH_RE = re.compile(rb"(?im)^content-length:\s*(\d+)")
# Höchstens so viele HTTPS-/Zielseiten-Verbindungen gleichzeitig. Jeder Treffer öffnet 1 + Zielseiten
# Verbindungen parallel – ohne Grenze wären das bei 2000 Workern schnell Tausende (EMFILE).
DETAIL_CONNECTIONS = 256
UNREACHABLE_ERRNOS = {errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ENETUNREACH, errno.ETIMEDOUT}
# Header, mit denen Proxys sich (oder den Client) verraten
PROXY_HEADERS = {
    "via", "x-forwarded-for", "forwarded", "x-real-ip", "client-ip", "x-client-ip",
    "x-proxy-id", "proxy-connection", "x-proxy-connection", "proxy-agent", "x-forwarded-host",
    "x-forwarded-proto", "x-bluecoat-via", "x-originating-ip",
}
ANONYMITY_RANK = {"transparent": 0, "anonymous": 1, "elite": 2}


async def wait_for(coro, timeout: float):
    """asyncio.wait_for, das beim Abbrechen keine unabgeholte Exception zurücklässt.

    Wird eine Prüfung per Strg+C abgebrochen, während ihr innerer Connect gerade scheitert,
    liefert Python < 3.12 den Verbindungsfehler statt CancelledError. Die innere Task endet
    dann mit einer Exception, die niemand abholt -> "Task exception was never retrieved"
    samt Traceback beim Beenden. Der Callback holt sie in jedem Fall ab.
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
    targets: Dict[str, bool] = field(default_factory=dict)  # Zielseiten-URL -> erreichbar?
    asn: int = 0            # Anbieter der Exit-IP (DB-IP), 0 = unbekannt
    org: str = ""
    hosting: Optional[bool] = None  # Exit vermutlich in einem Rechenzentrum? None = unbekannt


class Checker:
    def __init__(self, judge_ip: str, own_ips: Iterable[str], timeout: float, connect_timeout: float,
                 confirm_ip: Optional[str] = None, detail_timeout: Optional[float] = None,
                 detail_connect_timeout: Optional[float] = None,
                 targets: Sequence[Tuple[Target, str]] = (), https_test: bool = True,
                 judge: Judge = DEFAULT_JUDGE):
        self.use_judge(judge, judge_ip)
        # Ohne erreichbares Bestätigungsziel wird nicht bestätigt (sonst fiele jeder Proxy durch)
        self.confirm_ip_bytes = socket.inet_aton(confirm_ip) if confirm_ip else None
        # Mehrere möglich: z. B. echte IP per HTTPS, aber iCloud Private Relay/Firmenproxy auf Port 80
        self.own_ips = set(own_ips)
        self.timeout = timeout
        self._detail_slots: Optional[asyncio.Semaphore] = None
        self.https_test = https_test  # --fast: kein HTTPS-Test, Zielseiten aber trotzdem
        # Zielseiten mit vorab aufgelöster IP (SOCKS4 kann keine Hostnamen)
        self.targets = [(target, socket.inet_aton(ip)) for target, ip in targets]
        # Bestätigung und HTTPS-Test dürfen länger dauern als die (evtl. latenzbegrenzte) Basisprüfung
        self.detail_timeout = detail_timeout or timeout
        self.detail_connect_timeout = min(detail_connect_timeout or connect_timeout, self.detail_timeout)
        # Die allermeisten toten Proxys scheitern schon am TCP-Connect – die sollen
        # keinen Slot für den vollen Timeout blockieren.
        self.connect_timeout = min(connect_timeout, timeout)
        self.unreachable: Set[str] = set()

    def use_judge(self, judge: Judge, ip: str) -> None:
        """Prüfziel setzen oder mitten im Lauf wechseln (laufende Prüfungen nutzen noch das alte)."""
        self.judge = judge
        self.judge_ip = ip
        self.judge_ip_bytes = socket.inet_aton(ip)
        self.request = (
            f"GET {judge.path} HTTP/1.1\r\nHost: {judge.authority}\r\nUser-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        # HTTP-Proxys brauchen die absolute URL
        self.http_proxy_request = (
            f"GET http://{judge.authority}{judge.path} HTTP/1.1\r\nHost: {judge.authority}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\nProxy-Connection: close\r\n\r\n"
        ).encode()

    @property
    def confirms(self) -> bool:
        return self.confirm_ip_bytes is not None

    # ------------------------------------------------------------------ Basis

    async def check(self, key: str) -> Optional[CheckResult]:
        """Funktionierender Proxy -> CheckResult, sonst None."""
        ptype, proxy = split_key(key)
        start = time.perf_counter()
        try:
            body = await wait_for(self._check(ptype, proxy), self.timeout)
        except Exception:  # Timeout, Verbindungsfehler, kaputte Antworten – alles heißt "taugt nicht"
            return None

        if body is None:
            return None
        exit_ip = body.strip().decode("ascii", "ignore")
        try:
            ipaddress.IPv4Address(exit_ip)
        except ValueError:
            return None  # Proxy liefert Müll/Werbung/Login-Seite -> unbrauchbar
        if normalize_public_ip(exit_ip.encode()) != exit_ip:
            return None  # 127.0.0.1, 10.x & Co. sind keine echte Exit-IP – der Proxy antwortet selbst
        if exit_ip in self.own_ips:
            return None  # transparenter Proxy verrät deine echte IP
        return CheckResult(key, ptype, proxy, round((time.perf_counter() - start) * 1000), exit_ip)

    async def _check(self, ptype: str, proxy: str):
        # Viele ip:port stehen unter mehreren Typen in den Listen – wer schon beim
        # TCP-Connect scheitert, scheitert bei den anderen Typen genauso.
        ep = parse_endpoint(proxy)
        if ep.address in self.unreachable:
            return None
        # Ziel-IP und Anfrage zusammen festhalten – wechselt das Prüfziel mittendrin, passt beides noch
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
        """TCP-Verbindung zum Proxy. Nur die Basisprüfung merkt sich unerreichbare Proxys und nutzt den
        (evtl. latenzbegrenzten) kurzen Timeout – Detailprüfungen bekommen den normalen."""
        ep = parse_endpoint(proxy)
        timeout = self.detail_connect_timeout if detail else self.connect_timeout
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ep.host, ep.port), timeout)
        except (asyncio.TimeoutError, ConnectionRefusedError):
            if not detail:
                self.unreachable.add(ep.address)
            raise
        except OSError as e:
            # nicht z. B. EMFILE – das ist unser Fehler, nicht der des Proxys
            if not detail and e.errno in UNREACHABLE_ERRNOS:
                self.unreachable.add(ep.address)
            raise
        return reader, writer

    async def _handshake(self, ptype: str, ep: Endpoint, reader, writer, ip_bytes: bytes, port: int) -> bool:
        """SOCKS-Verbindung zu ip:port aufbauen; HTTP-Proxys brauchen keinen Handshake."""
        send, recv_exact = stream_io(reader, writer)
        if ptype == "socks4":
            return await socks4(send, recv_exact, ep, ip_bytes, port)
        if ptype == "socks5":
            return await socks5(send, recv_exact, ep, socks5_ipv4(ip_bytes), port)
        return True

    # ------------------------------------------------------------------ Bestätigung

    async def confirm(self, result: CheckResult) -> bool:
        """Zweite, unabhängige Anfrage über denselben Proxy. False = Fake/Honeypot oder instabil.

        Setzt dabei die Anonymitätsstufe aus den Headern, die beim Ziel ankommen.
        """
        if not self.confirms:
            return True
        try:
            body = await wait_for(self._confirm(result.ptype, result.proxy), self.detail_timeout)
        except Exception:  # Fehler bei der zweiten Anfrage heißt: nicht verlässlich
            return False
        anonymity = classify_confirmation(body, self.own_ips, result.exit_ip) if body is not None else None
        if anonymity is None:
            return False
        result.anonymity = anonymity
        return True

    async def _confirm(self, ptype: str, proxy: str) -> Optional[bytes]:
        ep = parse_endpoint(proxy)
        reader, writer = await self._connect(proxy, detail=True)
        try:
            if not await self._handshake(ptype, ep, reader, writer, self.confirm_ip_bytes, CONFIRM_PORT):
                return None
            writer.write(with_proxy_auth(HTTP_PROXY_CONFIRM_REQUEST, ep) if ptype == "http" else CONFIRM_REQUEST)
            await writer.drain()
            # Antwort kommt vom (nicht vertrauenswürdigen) Proxy – nur begrenzt viel lesen
            return await _read_http_200(reader)
        finally:
            writer.close()

    # ------------------------------------------------------------------ Details

    async def enrich(self, result: CheckResult) -> None:
        """HTTPS-Fähigkeit und Zielseiten ergänzen, alles parallel (die Anonymität kommt aus der Bestätigung)."""
        https = self._safe(self.check_https(result.ptype, result.proxy)) if self.https_test else _none()
        outcomes = await asyncio.gather(
            https,
            *(self._safe(self.check_target(result.ptype, result.proxy, t, ip)) for t, ip in self.targets),
        )
        result.https = bool(outcomes[0]) if self.https_test else None
        result.targets = {t.url: bool(ok) for (t, _), ok in zip(self.targets, outcomes[1:])}

    async def _safe(self, coro):
        if self._detail_slots is None:  # erst hier: vor Python 3.10 hängt ein Semaphor an der Event-Loop
            self._detail_slots = asyncio.Semaphore(DETAIL_CONNECTIONS)
        try:
            async with self._detail_slots:
                return await wait_for(coro, self.detail_timeout)
        except Exception:  # Detailprüfung fehlgeschlagen -> "nein"/"unbekannt", Basisergebnis bleibt
            return None

    async def check_https(self, ptype: str, proxy: str) -> bool:
        """Tunnel zum Prüfziel auf Port 443 + verifiziertes TLS + Exit-IP abrufen."""
        judge, ip_bytes, request = self.judge, self.judge_ip_bytes, self.request  # falls mittendrin gewechselt wird
        opened = await self._tls_tunnel(ptype, proxy, judge.host, ip_bytes, 443)
        if opened is None:
            return False
        reader, writer = opened
        try:
            writer.write(request)
            await writer.drain()
            # Nach verifiziertem TLS spricht hier der echte Server, nicht der Proxy
            status, _, body = await read_response(reader)
        finally:
            writer.close()
        try:
            ipaddress.IPv4Address(body.strip().decode("ascii", "ignore"))
        except ValueError:
            return False
        return status == 200

    async def check_target(self, ptype: str, proxy: str, target: Target, ip_bytes: bytes) -> bool:
        """Echte Anfrage an eine Zielseite durch den Proxy; 2xx/3xx = erreichbar.

        Gelesen wird nur der Antwortkopf – eine 500-KB-Startseite muss niemand herunterladen.
        """
        request = (
            f"GET {{path}} HTTP/1.1\r\nHost: {target.host_header}\r\nUser-Agent: {USER_AGENT}\r\n"
            f"Accept: text/html,*/*;q=0.8\r\nAccept-Language: de,en;q=0.8\r\nConnection: close\r\n\r\n"
        )
        if target.tls:
            opened = await self._tls_tunnel(ptype, proxy, target.host, ip_bytes, target.port)
            if opened is None:
                return False
            reader, writer = opened
            path = target.path
        else:
            reader, writer = await self._connect(proxy, detail=True)
            # HTTP-Proxys wollen für unverschlüsseltes HTTP die absolute URL
            path = target.url if ptype == "http" else target.path
        ep = parse_endpoint(proxy)
        try:
            # Handshake mit im try: scheitert er mit einer Exception, wird der Socket trotzdem geschlossen
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
        """Tunnel durch den Proxy zu host:port und darin verifiziertes TLS. None = Tunnel abgelehnt oder MITM."""
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
            return None  # Proxy bricht TLS auf (MITM) -> für HTTPS unbrauchbar
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
                    raise ConnectionError("Verbindung geschlossen")
                buf += chunk
            return buf

        if ptype == "http":
            connect = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode()
            await loop.sock_sendall(sock, with_proxy_auth(connect, ep))
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 8192:
                chunk = await loop.sock_recv(sock, 1)  # byteweise: nichts vom TLS-Strom verschlucken
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
    """Nur den Statuscode einer HTTP-Antwort lesen (Kopf höchstens 64 KiB)."""
    head = await reader.readuntil(b"\r\n\r\n")
    parts = head.split(b"\r\n", 1)[0].split()
    return int(parts[1]) if len(parts) > 1 and parts[0].startswith(b"HTTP/") and parts[1].isdigit() else 0


def confirmation_origins(body: bytes) -> Optional[List[str]]:
    """IPs aus einer httpbin-Antwort ("origin": "1.2.3.4" oder "1.2.3.4, 5.6.7.8"), None wenn unbrauchbar."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    # httpbin liefert immer "origin" und "headers" – fehlt eins, ist es nicht die erwartete Antwort
    if not isinstance(data, dict) or not isinstance(data.get("headers"), dict):
        return None
    origins = [part.strip() for part in str(data.get("origin", "")).split(",")]
    return [o for o in origins if _is_ipv4(o)] or None


def classify_confirmation(body: bytes, own_ips: Iterable[str], exit_ip: str) -> Optional[str]:
    """Antwort von httpbin.org/get prüfen -> Anonymitätsstufe, oder None bei unbrauchbarer Antwort.

    Honeypots liefern hier kein JSON mit gültiger Absender-IP. Außerdem muss der Proxy bei beiden
    Anfragen dieselbe Exit-IP zeigen – rotierende oder verkettete Ausgänge sind nicht verlässlich.
    """
    origins = confirmation_origins(body)
    if origins is None or exit_ip not in origins:
        return None
    return classify_anonymity(body, own_ips)


async def probe_confirm_target(ip: str, timeout: float, port: int = CONFIRM_PORT) -> bool:
    """Antwortet `ip` direkt (ohne Proxy) genau so, wie die Bestätigung es erwartet?

    Dieselbe Anfrage, dieselbe Größenbegrenzung, dieselbe Auswertung – und genau die IP, die später
    benutzt wird. Ein Redirect (z. B. auf HTTPS), ein Captive Portal oder eine Fehlerseite zählt nicht.
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
    except Exception:  # nicht erreichbar -> ohne Bestätigung weiter
        return False
    return body is not None and confirmation_origins(body) is not None


def _is_ipv4(text: str) -> bool:
    try:
        ipaddress.IPv4Address(text)
        return True
    except ValueError:
        return False


def classify_anonymity(body: bytes, own_ips: Iterable[str]) -> Optional[str]:
    """Antwort von httpbin.org (mit "headers") -> transparent / anonymous / elite."""
    if any(ip and ip.encode() in body for ip in own_ips):
        return "transparent"
    try:
        headers = json.loads(body).get("headers", {})
    except (ValueError, AttributeError):
        return None
    if not isinstance(headers, dict):
        return None  # unerwartete Antwort – nicht abstürzen, nur nicht bestätigen
    names = {str(name).lower() for name in headers}
    return "anonymous" if names & PROXY_HEADERS else "elite"


async def _read_http_200(reader) -> Optional[bytes]:
    """Liest eine kleine HTTP-Antwort; Body nur bei Status 200, sonst None."""
    data = bytearray()
    want = None  # Gesamtlänge laut Content-Length, sobald der Header da ist
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
                    return None  # früh aussteigen, Rest der Antwort ist egal
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
