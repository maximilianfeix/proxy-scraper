"""Minimal HTTP client on plain asyncio + ssl – for sources, APIs and check targets."""

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

# hosts whose certificate couldn't be verified (typically: a firewall with TLS inspection like Sophos)
INSECURE_HOSTS: Set[str] = set()


@lru_cache(maxsize=None)
def ssl_context() -> ssl.SSLContext:
    # build once instead of per connection – otherwise loading the CA file blocks the event loop every time
    try:
        import certifi  # python.org Python on macOS often has no system certificates

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
    """One HTTP/1.1 request -> (status, headers, body). Follows redirects for GET.

    If certificate verification fails, it is only retried unverified for GETs without a body and without
    custom headers – so for public proxy lists, never with API tokens or sent data. The only headers
    allowed are If-None-Match / If-Modified-Since (ETag cache), which carry no secret.
    The lists are public, and every proxy from them gets checked on its own anyway.
    """
    extra = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())
    if body is not None:
        extra += f"Content-Length: {len(body)}\r\n"
    for _ in range(max_redirects + 1):
        u = urlsplit(url)
        https = u.scheme == "https"
        port = u.port or (443 if https else 80)
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        # unverified only for GETs without a body and without custom headers (except the conditional ETag headers,
        # they carry no secret). Never tokens or sent data over an unverified connection.
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
    raise ConnectionError("too many redirects")


async def http_get(
    url: str, timeout: float = 15.0, max_redirects: int = 3, headers: Optional[Dict[str, str]] = None
) -> bytes:
    """GET that raises an exception for anything but 200."""
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

    # respect Content-Length: servers with keep-alive (e.g. checkip.amazonaws.com) don't close
    # the connection otherwise, and reading to the end would run into the timeout.
    if headers.get(b"transfer-encoding", b"").lower() == b"chunked":
        body = dechunk(await read_all(reader))
    elif headers.get(b"content-length", b"").isdigit():
        length = int(headers[b"content-length"])
        if length > MAX_BODY:
            raise ConnectionError("response too large")
        body = await reader.readexactly(length)
    else:
        body = await read_all(reader)
    return status, headers, body


async def read_all(reader, limit: int = MAX_BODY) -> bytes:
    # some servers (e.g. Cloudflare) end with RST instead of FIN – keep the data already read
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
