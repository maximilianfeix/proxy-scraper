"""Verbindung zum Ziel über einen Proxy aus dem Pool aufbauen (HTTP CONNECT, SOCKS4, SOCKS5)."""

from __future__ import annotations

import asyncio
import socket

from ..handshake import parse_endpoint, socks4, socks5, socks5_domain, stream_io, with_proxy_auth
from .pool import PoolEntry


class UpstreamError(Exception):
    """Der gewählte Proxy hat die Verbindung nicht aufgebaut – nächster Versuch."""


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


async def _resolve(host: str, port: int) -> str:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, family=socket.AF_INET)
    return infos[0][4][0]
