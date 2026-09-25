"""Connect to the target through a proxy from the pool (HTTP CONNECT, SOCKS4, SOCKS5)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

from ..handshake import (
    ProxyRefused,
    parse_endpoint,
    socks4_connect,
    socks5_connect,
    socks5_domain,
    socks5_ipv4,
    stream_io,
    with_proxy_auth,
)
from .pool import PoolEntry


class UpstreamError(Exception):
    """The chosen proxy didn't establish the connection – next attempt."""


class TargetError(UpstreamError):
    """The proxy answered but couldn't open the connection to the target (refused tunnel, 502/504, target
    not resolvable). That may be the target's fault, so it only counts against the proxy if another
    proxy reaches the same target."""


class Unsupported(UpstreamError):
    """This proxy type can't do this target at all (SOCKS4 and IPv6). Never counts against the proxy."""


GATEWAY_ERRORS = (b"502", b"503", b"504")


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
        if isinstance(e, UpstreamError):
            raise
        if isinstance(e, (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError)):
            raise UpstreamError(f"tunnel failed: {e!r}") from None
        raise
    return reader, writer


async def _handshake(ptype: str, proxy: str, reader, writer, host: str, port: int) -> None:
    try:
        await _connect_through(ptype, proxy, reader, writer, host, port)
    except ProxyRefused as e:  # the proxy speaks the protocol fine, only the CONNECT to the target failed
        raise TargetError(str(e)) from None


async def _connect_through(ptype: str, proxy: str, reader, writer, host: str, port: int) -> None:
    ep = parse_endpoint(proxy)
    literal = _ip_literal(host)
    if ptype == "http":
        authority = f"[{host}]:{port}" if literal and literal.version == 6 else f"{host}:{port}"
        connect = f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode()
        writer.write(with_proxy_auth(connect, ep))
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        first = head.split(b"\r\n", 1)[0]
        parts = first.split()
        # exactly 200 – "HTTP/1.1 2000" or similar is not an established tunnel
        if len(parts) < 2 or not parts[0].startswith(b"HTTP/") or parts[1] != b"200":
            error = TargetError if len(parts) > 1 and parts[1] in GATEWAY_ERRORS else UpstreamError
            raise error(first.decode("latin-1"))
    elif ptype == "socks4":
        if literal and literal.version == 6:
            raise Unsupported("SOCKS4 can't reach IPv6 targets")
        ip = await _resolve(host, port)  # SOCKS4 only knows IPv4 addresses
        if not await socks4_connect(*stream_io(reader, writer), ep, socket.inet_aton(ip), port):
            raise UpstreamError("no SOCKS4 answer")
    else:
        if literal and literal.version == 6:
            address = b"\x04" + literal.packed
        elif literal:
            address = socks5_ipv4(literal.packed)
        else:
            address = socks5_domain(host)  # host name instead of IP: resolved at the proxy (no DNS leak)
        if not await socks5_connect(*stream_io(reader, writer), ep, address, port):
            raise UpstreamError("SOCKS5 greeting or login failed")


def _ip_literal(host: str):
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


async def _resolve(host: str, port: int) -> str:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, family=socket.AF_INET)
    except OSError as e:  # no IPv4 address for the target – a SOCKS4 limit, not the proxy's fault
        raise Unsupported(f"can't resolve {host} to IPv4: {e}") from None
    return infos[0][4][0]
