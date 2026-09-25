"""Minimaler HTTP-Client auf reinem asyncio + ssl – für Quellen, APIs und Prüfziele."""

from __future__ import annotations

import asyncio
import ssl
from functools import lru_cache
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urljoin, urlsplit

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
MAX_BODY = 64 * 1024 * 1024

# Hosts, deren Zertifikat nicht prüfbar war (typisch: Firewall mit TLS-Inspektion wie Sophos)
INSECURE_HOSTS: Set[str] = set()


@lru_cache(maxsize=None)
def ssl_context() -> ssl.SSLContext:
    # Einmal bauen statt pro Verbindung – das Laden der CA-Datei blockiert sonst jedes Mal die Event-Loop
    try:
        import certifi  # python.org-Python auf macOS hat oft keine System-Zertifikate

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


@lru_cache(maxsize=None)
def _insecure_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


CONDITIONAL_HEADERS = {"If-None-Match", "If-Modified-Since"}


async def http_request(
    url: str,
    timeout: float = 15.0,
    headers: Optional[Dict[str, str]] = None,
    method: str = "GET",
    body: Optional[bytes] = None,
    max_redirects: int = 3,
    insecure_fallback: bool = True,
) -> Tuple[int, Dict[bytes, bytes], bytes]:
    """Eine HTTP/1.1-Anfrage -> (Status, Header, Body). Folgt Redirects bei GET.

    Schlägt die Zertifikatsprüfung fehl, wird nur bei GETs ohne Body und ohne eigene Header unverifiziert
    wiederholt – also bei öffentlichen Proxy-Listen, nie mit API-Token oder gesendeten Daten. Einzige
    erlaubte Header sind If-None-Match / If-Modified-Since (ETag-Cache), die tragen kein Geheimnis.
    Die Listen sind öffentlich, und jeder Proxy daraus wird ohnehin selbst geprüft.
    """
    extra = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())
    if body is not None:
        extra += f"Content-Length: {len(body)}\r\n"
    for _ in range(max_redirects + 1):
        u = urlsplit(url)
        https = u.scheme == "https"
        port = u.port or (443 if https else 80)
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        # Unverifiziert nur für GETs ohne Body und ohne eigene Header (bedingte ETag-Header ausgenommen,
        # die tragen kein Geheimnis). Token oder gesendete Daten nie über eine ungeprüfte Verbindung.
        insecure_ok = insecure_fallback and method == "GET" and body is None and \
            set(headers or ()) <= CONDITIONAL_HEADERS
        reader, writer = await _connect(u.hostname, port, https, allow_insecure=insecure_ok, timeout=timeout)
        try:
            writer.write(
                f"{method} {path} HTTP/1.1\r\nHost: {u.hostname}\r\nUser-Agent: {USER_AGENT}\r\n"
                f"Accept: */*\r\nAccept-Encoding: identity\r\n{extra}Connection: close\r\n\r\n".encode()
                + (body or b"")
            )
            await writer.drain()
            status, resp_headers, resp_body = await asyncio.wait_for(read_response(reader), timeout)
        finally:
            writer.close()

        if method == "GET" and status in (301, 302, 303, 307, 308) and b"location" in resp_headers:
            url = urljoin(url, resp_headers[b"location"].decode())
            continue
        return status, resp_headers, resp_body
    raise ConnectionError("zu viele Redirects")


async def http_get(
    url: str, timeout: float = 15.0, max_redirects: int = 3, headers: Optional[Dict[str, str]] = None
) -> bytes:
    """GET, der bei allem außer 200 eine Ausnahme wirft."""
    status, _, body = await http_request(url, timeout, headers, max_redirects=max_redirects)
    if status != 200:
        raise ConnectionError(f"HTTP {status}")
    return body


async def _connect(host: str, port: int, https: bool, allow_insecure: bool, timeout: float):
    if not https:
        return await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    ctx = _insecure_ssl_context() if allow_insecure and host in INSECURE_HOSTS else ssl_context()
    try:
        return await asyncio.wait_for(asyncio.open_connection(host, port, ssl=ctx, server_hostname=host), timeout)
    except ssl.SSLCertVerificationError:
        if not allow_insecure:
            raise
        INSECURE_HOSTS.add(host)
        return await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=_insecure_ssl_context(), server_hostname=host), timeout
        )


async def read_response(reader) -> Tuple[int, Dict[bytes, bytes], bytes]:
    head = await reader.readuntil(b"\r\n\r\n")
    lines = head[:-4].split(b"\r\n")
    parts = lines[0].split()
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    headers: Dict[bytes, bytes] = {}
    for line in lines[1:]:
        k, _, v = line.partition(b":")
        headers[k.strip().lower()] = v.strip()

    # Content-Length beachten: Server mit keep-alive (z. B. checkip.amazonaws.com) schließen
    # die Verbindung sonst nicht, und Lesen bis zum Ende liefe in den Timeout.
    if headers.get(b"transfer-encoding", b"").lower() == b"chunked":
        body = dechunk(await read_all(reader))
    elif headers.get(b"content-length", b"").isdigit():
        length = int(headers[b"content-length"])
        if length > MAX_BODY:
            raise ConnectionError("Antwort zu groß")
        body = await reader.readexactly(length)
    else:
        body = await read_all(reader)
    return status, headers, body


async def read_all(reader, limit: int = MAX_BODY) -> bytes:
    # Manche Server (z. B. Cloudflare) beenden mit RST statt FIN – bereits gelesene Daten behalten
    buf = bytearray()
    while len(buf) < limit:
        try:
            chunk = await reader.read(65536)
        except ConnectionResetError:
            break
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


def dechunk(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        j = data.find(b"\r\n", i)
        if j < 0:
            break
        try:
            size = int(data[i:j].split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        out += data[j + 2 : j + 2 + size]
        i = j + 2 + size + 2
    return bytes(out)
