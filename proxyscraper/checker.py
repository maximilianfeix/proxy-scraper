"""Proxy-Prüfung mit eigenen Protokoll-Handshakes (HTTP, SOCKS4, SOCKS5).

Basisprüfung: eine TCP-Verbindung pro Proxy, Abruf der Exit-IP über checkip.amazonaws.com.
Detailprüfung (nur für funktionierende Proxys, also wenige):
  - HTTPS: Tunnel zu Port 443 aufbauen und darin eine verifizierte TLS-Verbindung – scheitert bei
    Proxys, die kein CONNECT können oder TLS aufbrechen (MITM).
  - Anonymität (nur HTTP-Proxys): Welche Header kommen beim Ziel an? SOCKS-Proxys fassen den
    Datenstrom nicht an und sind damit immer "elite".
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
from dataclasses import dataclass
from typing import Iterable, Optional, Set

from .netio import USER_AGENT, dechunk, read_response, ssl_context
from .parsing import split_key

# Prüfziel: liefert die IP zurück, die beim Server ankommt (nur Text, sehr klein).
# Bewusst NICHT hinter Cloudflare – sonst "funktionieren" beliebige Cloudflare-IPs als Fake-Proxy.
JUDGE_HOST = "checkip.amazonaws.com"
JUDGE_PORT = 80
# Zeigt die empfangenen Header – für die Anonymitätsstufe von HTTP-Proxys
HEADERS_JUDGE_HOST = "httpbin.org"

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


class Checker:
    def __init__(self, judge_ip: str, own_ips: Iterable[str], timeout: float, connect_timeout: float):
        self.judge_ip = judge_ip
        self.judge_ip_bytes = socket.inet_aton(judge_ip)
        # Mehrere möglich: z. B. echte IP per HTTPS, aber iCloud Private Relay/Firmenproxy auf Port 80
        self.own_ips = set(own_ips)
        self.timeout = timeout
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
        # Bewusst ohne Proxy-Connection-Header – der würde sonst selbst als Proxy-Spur auftauchen
        self.headers_request = (
            f"GET http://{HEADERS_JUDGE_HOST}/headers HTTP/1.1\r\nHost: {HEADERS_JUDGE_HOST}\r\n"
            f"User-Agent: {USER_AGENT}\r\nAccept: */*\r\nConnection: close\r\n\r\n"
        ).encode()

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
        host, port = proxy.rsplit(":", 1)
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), self.connect_timeout)
        except (asyncio.TimeoutError, ConnectionRefusedError):
            self.unreachable.add(proxy)
            raise
        except OSError as e:
            if e.errno in UNREACHABLE_ERRNOS:  # nicht z. B. EMFILE – das ist unser Fehler, nicht der des Proxys
                self.unreachable.add(proxy)
            raise
        try:
            return await self._talk(ptype, reader, writer)
        finally:
            writer.close()

    async def _talk(self, ptype: str, reader, writer):
        if ptype == "http":
            writer.write(self.http_proxy_request)
        elif ptype == "socks4":
            writer.write(b"\x04\x01" + JUDGE_PORT.to_bytes(2, "big") + self.judge_ip_bytes + b"\x00")
            await writer.drain()
            resp = await reader.readexactly(8)
            if resp[1] != 0x5A:
                return None
            writer.write(self.request)
        else:  # socks5
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            if await reader.readexactly(2) != b"\x05\x00":
                return None
            writer.write(b"\x05\x01\x00\x01" + self.judge_ip_bytes + JUDGE_PORT.to_bytes(2, "big"))
            await writer.drain()
            if not await _socks5_reply_ok(reader.readexactly):
                return None
            writer.write(self.request)

        await writer.drain()
        return await _read_http_200(reader)

    # ------------------------------------------------------------------ Details

    async def enrich(self, result: CheckResult) -> None:
        """HTTPS-Fähigkeit und Anonymität ergänzen (beides parallel)."""
        https, anonymity = await asyncio.gather(
            self._safe(self.check_https(result.ptype, result.proxy)),
            self._safe(self.check_anonymity(result.ptype, result.proxy)),
        )
        result.https = bool(https)
        result.anonymity = anonymity or ""

    async def _safe(self, coro):
        try:
            return await wait_for(coro, self.timeout)
        except Exception:  # Detailprüfung fehlgeschlagen -> "nein"/"unbekannt", Basisergebnis bleibt
            return None

    async def check_anonymity(self, ptype: str, proxy: str) -> Optional[str]:
        if ptype != "http":
            return "elite"
        host, port = proxy.rsplit(":", 1)
        reader, writer = await asyncio.open_connection(host, int(port))
        try:
            writer.write(self.headers_request)
            await writer.drain()
            status, _, body = await read_response(reader)
        finally:
            writer.close()
        if status != 200:
            return None
        return classify_anonymity(body, self.own_ips)

    async def check_https(self, ptype: str, proxy: str) -> bool:
        """Tunnel zu JUDGE_HOST:443 + verifiziertes TLS + Exit-IP abrufen."""
        loop = asyncio.get_running_loop()
        host, port = proxy.rsplit(":", 1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            await loop.sock_connect(sock, (host, int(port)))
            if not await self._open_tunnel(loop, sock, ptype, 443):
                sock.close()
                return False
            reader, writer = await asyncio.open_connection(sock=sock, ssl=ssl_context(), server_hostname=JUDGE_HOST)
        except ssl.SSLCertVerificationError:
            sock.close()
            return False  # Proxy bricht TLS auf (MITM) -> für HTTPS unbrauchbar
        except BaseException:
            sock.close()
            raise
        try:
            writer.write(self.request)
            await writer.drain()
            status, _, body = await read_response(reader)
        finally:
            writer.close()
        try:
            ipaddress.IPv4Address(body.strip().decode("ascii", "ignore"))
        except ValueError:
            return False
        return status == 200

    async def _open_tunnel(self, loop, sock: socket.socket, ptype: str, port: int) -> bool:
        async def recv_exact(n: int) -> bytes:
            buf = b""
            while len(buf) < n:
                chunk = await loop.sock_recv(sock, n - len(buf))
                if not chunk:
                    raise ConnectionError("Verbindung geschlossen")
                buf += chunk
            return buf

        if ptype == "http":
            await loop.sock_sendall(
                sock, f"CONNECT {JUDGE_HOST}:{port} HTTP/1.1\r\nHost: {JUDGE_HOST}:{port}\r\n\r\n".encode()
            )
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 8192:
                chunk = await loop.sock_recv(sock, 1)  # byteweise: nichts vom TLS-Strom verschlucken
                if not chunk:
                    return False
                head += chunk
            first = head.split(b"\r\n", 1)[0]
            return first.startswith(b"HTTP/") and b" 200" in first
        if ptype == "socks4":
            await loop.sock_sendall(sock, b"\x04\x01" + port.to_bytes(2, "big") + self.judge_ip_bytes + b"\x00")
            return (await recv_exact(8))[1] == 0x5A
        await loop.sock_sendall(sock, b"\x05\x01\x00")
        if await recv_exact(2) != b"\x05\x00":
            return False
        await loop.sock_sendall(sock, b"\x05\x01\x00\x01" + self.judge_ip_bytes + port.to_bytes(2, "big"))
        return await _socks5_reply_ok(recv_exact)


def classify_anonymity(body: bytes, own_ips: Iterable[str]) -> Optional[str]:
    """Antwort von httpbin.org/headers -> transparent / anonymous / elite."""
    if any(ip and ip.encode() in body for ip in own_ips):
        return "transparent"
    try:
        headers = json.loads(body).get("headers", {})
    except ValueError:
        return None
    names = {name.lower() for name in headers}
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
