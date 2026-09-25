"""Connect to the target through a proxy from the pool (HTTP CONNECT, SOCKS4, SOCKS5)."""

from __future__ import annotations

import asyncio
import socket

from ..handshake import parse_endpoint, socks4, socks5, socks5_domain, stream_io, with_proxy_auth
from .pool import PoolEntry


class UpstreamError(Exception):
    """The chosen proxy didn't establish the connection – next attempt."""


async def open_upstream(entry: PoolEntry, host: str, port: int, timeout: float, tunnel: bool = True):
    """Connection through the proxy to host:port. tunnel=False means: HTTP upstream in forwarding mode
    (classic proxy request without CONNECT). Raises UpstreamError if the proxy doesn't play along."""
    r = entry.result
    ep = parse_endpoint(r.proxy)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ep.host, ep.port), timeout)
    except (OSError, asyncio.TimeoutError) as e:
        raise UpstreamError(f"proxy unreachable: {e!r}") from None
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
        # exactly 200 – "HTTP/1.1 2000" or similar is not an established tunnel
        if len(parts) < 2 or not parts[0].startswith(b"HTTP/") or parts[1] != b"200":
            raise UpstreamError(first.decode("latin-1"))
    elif ptype == "socks4":
        ip = await _resolve(host, port)  # SOCKS4 only knows IPv4 addresses
        if not await socks4(*stream_io(reader, writer), ep, socket.inet_aton(ip), port):
            raise UpstreamError("SOCKS4 abgelehnt")
    else:
        # host name instead of IP: name resolution happens at the proxy (no DNS leak)
        if not await socks5(*stream_io(reader, writer), ep, socks5_domain(host), port):
            raise UpstreamError("SOCKS5 abgelehnt")


async def _resolve(host: str, port: int) -> str:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, family=socket.AF_INET)
    return infos[0][4][0]
