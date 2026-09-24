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

from .netio import USER_AGENT, dechunk, read_response, ssl_context
from .parsing import split_key
from .targets import Target

# Prüfziel: liefert die IP zurück, die beim Server ankommt (nur Text, sehr klein).
# Bewusst NICHT hinter Cloudflare – sonst "funktionieren" beliebige Cloudflare-IPs als Fake-Proxy.
JUDGE_HOST = "checkip.amazonaws.com"
JUDGE_PORT = 80
# Zweites, unabhängiges Prüfziel: liefert JSON mit Absender-IP ("origin") und empfangenen Headern
CONFIRM_HOST = "httpbin.org"
CONFIRM_PORT = 80
# Bewusst ohne Proxy-Connection-Header – der würde sonst selbst als Proxy-Spur auftauchen
_CONFIRM_HEADERS = f"Host: {CONFIRM_HOST}\r\nUser-Agent: {USER_AGENT}\r\nAccept: */*\r\nConnection: close\r\n\r\n"
CONFIRM_REQUEST = f"GET /get HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()
HTTP_PROXY_CONFIRM_REQUEST = f"GET http://{CONFIRM_HOST}/get HTTP/1.1\r\n{_CONFIRM_HEADERS}".encode()

CONTENT_LENGTH_RE = re.compile(rb"(?im)^content-length:\s*(\d+)")
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


class Checker:
    def __init__(self, judge_ip: str, own_ips: Iterable[str], timeout: float, connect_timeout: float,
                 confirm_ip: Optional[str] = None, detail_timeout: Optional[float] = None,
                 detail_connect_timeout: Optional[float] = None,
                 targets: Sequence[Tuple[Target, str]] = ()):
        self.judge_ip = judge_ip
        self.judge_ip_bytes = socket.inet_aton(judge_ip)
        # Ohne erreichbares Bestätigungsziel wird nicht bestätigt (sonst fiele jeder Proxy durch)
        self.confirm_ip_bytes = socket.inet_aton(confirm_ip) if confirm_ip else None
        # Mehrere möglich: z. B. echte IP per HTTPS, aber iCloud Private Relay/Firmenproxy auf Port 80
        self.own_ips = set(own_ips)
        self.timeout = timeout
        # Zielseiten mit vorab aufgelöster IP (SOCKS4 kann keine Hostnamen)
        self.targets = [(target, socket.inet_aton(ip)) for target, ip in targets]
        # Bestätigung und HTTPS-Test dürfen länger dauern als die (evtl. latenzbegrenzte) Basisprüfung
        self.detail_timeout = detail_timeout or timeout
        self.detail_connect_timeout = min(detail_connect_timeout or connect_timeout, self.detail_timeout)
        # Die allermeisten toten Proxys scheitern schon am TCP-Connect – die sollen
        # keinen Slot für den vollen Timeout blockieren.
        self.connect_timeout = min(connect_timeout, timeout)
        self.unreachable: Set[str] = set()
        self.request = (
            f"GET / HTTP/1.1\r\nHost: {JUDGE_HOST}\r\nUser-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        # HTTP-Proxys brauchen die absolute URL
        self.http_proxy_request = (
            f"GET http://{JUDGE_HOST}/ HTTP/1.1\r\nHost: {JUDGE_HOST}\r\nUser-Agent: Mozilla/5.0\r\n"
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
        if exit_ip in self.own_ips:
            return None  # transparenter Proxy verrät deine echte IP
        return CheckResult(key, ptype, proxy, round((time.perf_counter() - start) * 1000), exit_ip)

    async def _check(self, ptype: str, proxy: str):
        # Viele ip:port stehen unter mehreren Typen in den Listen – wer schon beim
        # TCP-Connect scheitert, scheitert bei den anderen Typen genauso.
        if proxy in self.unreachable:
            return None
        reader, writer = await self._connect(proxy)
        try:
            if not await self._handshake(ptype, reader, writer, self.judge_ip_bytes, JUDGE_PORT):
                return None
            writer.write(self.http_proxy_request if ptype == "http" else self.request)
            await writer.drain()
            return await _read_http_200(reader)
        finally:
            writer.close()

    async def _connect(self, proxy: str, detail: bool = False):
        """TCP-Verbindung zum Proxy. Nur die Basisprüfung merkt sich unerreichbare Proxys und nutzt den
        (evtl. latenzbegrenzten) kurzen Timeout – Detailprüfungen bekommen den normalen."""
        host, port = proxy.rsplit(":", 1)
        timeout = self.detail_connect_timeout if detail else self.connect_timeout
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout)
        except (asyncio.TimeoutError, ConnectionRefusedError):
            if not detail:
                self.unreachable.add(proxy)
            raise
        except OSError as e:
            # nicht z. B. EMFILE – das ist unser Fehler, nicht der des Proxys
            if not detail and e.errno in UNREACHABLE_ERRNOS:
                self.unreachable.add(proxy)
            raise
        return reader, writer

    async def _handshake(self, ptype: str, reader, writer, ip_bytes: bytes, port: int) -> bool:
        """SOCKS-Verbindung zu ip:port aufbauen; HTTP-Proxys brauchen keinen Handshake."""
        if ptype == "socks4":
            writer.write(b"\x04\x01" + port.to_bytes(2, "big") + ip_bytes + b"\x00")
            await writer.drain()
            return (await reader.readexactly(8))[1] == 0x5A
        if ptype == "socks5":
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            if await reader.readexactly(2) != b"\x05\x00":
                return False
            writer.write(b"\x05\x01\x00\x01" + ip_bytes + port.to_bytes(2, "big"))
            await writer.drain()
            return await _socks5_reply_ok(reader.readexactly)
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
        reader, writer = await self._connect(proxy, detail=True)
        try:
            if not await self._handshake(ptype, reader, writer, self.confirm_ip_bytes, CONFIRM_PORT):
                return None
            writer.write(HTTP_PROXY_CONFIRM_REQUEST if ptype == "http" else CONFIRM_REQUEST)
            await writer.drain()
            # Antwort kommt vom (nicht vertrauenswürdigen) Proxy – nur begrenzt viel lesen
            return await _read_http_200(reader)
        finally:
            writer.close()

    # ------------------------------------------------------------------ Details

    async def enrich(self, result: CheckResult) -> None:
        """HTTPS-Fähigkeit und Zielseiten ergänzen, alles parallel (die Anonymität kommt aus der Bestätigung)."""
        outcomes = await asyncio.gather(
            self._safe(self.check_https(result.ptype, result.proxy)),
            *(self._safe(self.check_target(result.ptype, result.proxy, t, ip)) for t, ip in self.targets),
        )
        result.https = bool(outcomes[0])
        result.targets = {t.url: bool(ok) for (t, _), ok in zip(self.targets, outcomes[1:])}

    async def _safe(self, coro):
        try:
            return await wait_for(coro, self.detail_timeout)
        except Exception:  # Detailprüfung fehlgeschlagen -> "nein"/"unbekannt", Basisergebnis bleibt
            return None

    async def check_https(self, ptype: str, proxy: str) -> bool:
        """Tunnel zu JUDGE_HOST:443 + verifiziertes TLS + Exit-IP abrufen."""
        opened = await self._tls_tunnel(ptype, proxy, JUDGE_HOST, self.judge_ip_bytes, 443)
        if opened is None:
            return False
        reader, writer = opened
        try:
            writer.write(self.request)
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
            if not await self._handshake(ptype, reader, writer, ip_bytes, target.port):
                writer.close()
                return False
            # HTTP-Proxys wollen für unverschlüsseltes HTTP die absolute URL
            path = target.url if ptype == "http" else target.path
        try:
            writer.write(request.format(path=path).encode())
            await writer.drain()
            status = await _read_status(reader)
        finally:
            writer.close()
        return 200 <= status < 400

    async def _tls_tunnel(self, ptype: str, proxy: str, host: str, ip_bytes: bytes, port: int):
        """Tunnel durch den Proxy zu host:port und darin verifiziertes TLS. None = Tunnel abgelehnt oder MITM."""
        loop = asyncio.get_running_loop()
        proxy_host, proxy_port = proxy.rsplit(":", 1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            await loop.sock_connect(sock, (proxy_host, int(proxy_port)))
            if not await self._open_tunnel(loop, sock, ptype, host, ip_bytes, port):
                sock.close()
                return None
            return await asyncio.open_connection(sock=sock, ssl=ssl_context(), server_hostname=host)
        except ssl.SSLCertVerificationError:
            sock.close()
            return None  # Proxy bricht TLS auf (MITM) -> für HTTPS unbrauchbar
        except BaseException:
            sock.close()
            raise

    async def _open_tunnel(self, loop, sock: socket.socket, ptype: str, host: str, ip_bytes: bytes, port: int) -> bool:
        async def recv_exact(n: int) -> bytes:
            buf = b""
            while len(buf) < n:
                chunk = await loop.sock_recv(sock, n - len(buf))
                if not chunk:
                    raise ConnectionError("Verbindung geschlossen")
                buf += chunk
            return buf

        if ptype == "http":
            await loop.sock_sendall(sock, f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 8192:
                chunk = await loop.sock_recv(sock, 1)  # byteweise: nichts vom TLS-Strom verschlucken
                if not chunk:
                    return False
                head += chunk
            first = head.split(b"\r\n", 1)[0]
            return first.startswith(b"HTTP/") and b" 200" in first
        if ptype == "socks4":
            await loop.sock_sendall(sock, b"\x04\x01" + port.to_bytes(2, "big") + ip_bytes + b"\x00")
            return (await recv_exact(8))[1] == 0x5A
        await loop.sock_sendall(sock, b"\x05\x01\x00")
        if await recv_exact(2) != b"\x05\x00":
            return False
        await loop.sock_sendall(sock, b"\x05\x01\x00\x01" + ip_bytes + port.to_bytes(2, "big"))
        return await _socks5_reply_ok(recv_exact)


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


async def _socks5_reply_ok(read_exact) -> bool:
    resp = await read_exact(4)
    if resp[1] != 0x00:
        return False
    atyp = resp[3]
    if atyp == 1:
        await read_exact(4 + 2)
    elif atyp == 4:
        await read_exact(16 + 2)
    elif atyp == 3:
        ln = (await read_exact(1))[0]
        await read_exact(ln + 2)
    else:
        return False
    return True


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
