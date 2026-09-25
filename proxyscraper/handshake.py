"""Connecting through HTTP, SOCKS4 and SOCKS5 proxies – for the checker and the proxy server.

Proxies with credentials appear as "user:pass@ip:port" in the key, user and password
URL-encoded (otherwise ":" or "@" in the password would mess everything up).

The functions get send/recv_exact instead of a stream because the HTTPS test works with
bare sockets and everything else with asyncio streams.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import quote, unquote

Send = Callable[[bytes], Awaitable[None]]
RecvExact = Callable[[int], Awaitable[bytes]]

SOCKS5_NO_AUTH = 0x00
SOCKS5_USER_PASS = 0x02  # RFC 1929


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    user: str = ""
    password: str = ""

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def has_auth(self) -> bool:
        return bool(self.user)


def parse_endpoint(proxy: str) -> Endpoint:
    """'user:pass@1.2.3.4:1080' or '1.2.3.4:1080' -> Endpoint."""
    auth, _, address = proxy.rpartition("@")
    host, _, port = address.rpartition(":")
    user, _, password = auth.partition(":")
    return Endpoint(host, int(port), unquote(user), unquote(password))


def format_auth(user: str, password: str) -> str:
    """Encode user and password the way they appear in the key ('' without a user)."""
    if not user:
        return ""
    return quote(user, safe="") + (":" + quote(password, safe="") if password else "")


def proxy_authorization(ep: Endpoint) -> bytes:
    """Header line for HTTP proxies (incl. \\r\\n), empty without credentials."""
    if not ep.has_auth:
        return b""
    token = base64.b64encode(f"{ep.user}:{ep.password}".encode()).decode()
    return f"Proxy-Authorization: Basic {token}\r\n".encode()


def with_proxy_auth(request: bytes, ep: Endpoint) -> bytes:
    """Appends Proxy-Authorization to the head of a finished HTTP request (ends with \\r\\n\\r\\n)."""
    header = proxy_authorization(ep)
    return request[:-2] + header + b"\r\n" if header else request


class ProxyRefused(Exception):
    """The proxy answered, but the CONNECT to the target was refused – it spoke the protocol fine."""


async def socks4(send: Send, recv_exact: RecvExact, ep: Endpoint, ip_bytes: bytes, port: int) -> bool:
    """SOCKS4 CONNECT; the user name goes into the user ID field (SOCKS4 has no password)."""
    return await socks4_connect(send, recv_exact, ep, ip_bytes, port, strict=False)


async def socks4_connect(send: Send, recv_exact: RecvExact, ep: Endpoint, ip_bytes: bytes, port: int,
                         strict: bool = True) -> bool:
    """strict: a proper SOCKS4 reply that refuses the CONNECT (0x5B–0x5D) raises ProxyRefused,
    anything that isn't a SOCKS4 reply at all returns False."""
    await send(b"\x04\x01" + port.to_bytes(2, "big") + ip_bytes + ep.user.encode()[:255] + b"\x00")
    reply = await recv_exact(8)
    if reply[1] == 0x5A:
        return True
    if strict and reply[0] == 0x00 and reply[1] in (0x5B, 0x5C, 0x5D):
        raise ProxyRefused(f"SOCKS4 reply 0x{reply[1]:02x}")
    return False


async def socks5(send: Send, recv_exact: RecvExact, ep: Endpoint, address: bytes, port: int) -> bool:
    """SOCKS5 CONNECT to address (ATYP + address, see socks5_ipv4/socks5_domain)."""
    return await socks5_connect(send, recv_exact, ep, address, port, strict=False)


async def socks5_connect(send: Send, recv_exact: RecvExact, ep: Endpoint, address: bytes, port: int,
                         strict: bool = True) -> bool:
    """strict: greeting and login are the proxy's part (False on failure); a refused CONNECT after a
    successful greeting raises ProxyRefused, because then the proxy works and only the target failed."""
    methods = bytes([SOCKS5_NO_AUTH, SOCKS5_USER_PASS]) if ep.has_auth else bytes([SOCKS5_NO_AUTH])
    await send(b"\x05" + bytes([len(methods)]) + methods)
    reply = await recv_exact(2)
    if reply[0] != 0x05:
        return False
    if reply[1] == SOCKS5_USER_PASS and ep.has_auth:
        user, password = ep.user.encode(), ep.password.encode()
        if len(user) > 255 or len(password) > 255:
            return False
        await send(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
        if (await recv_exact(2))[1] != 0x00:
            return False  # login refused
    elif reply[1] != SOCKS5_NO_AUTH:
        return False
    await send(b"\x05\x01\x00" + address + port.to_bytes(2, "big"))
    if await socks5_reply_ok(recv_exact):
        return True
    if strict:
        raise ProxyRefused("SOCKS5 refused the CONNECT")
    return False


def socks5_ipv4(ip_bytes: bytes) -> bytes:
    return b"\x01" + ip_bytes


def socks5_domain(host: str) -> bytes:
    name = host.encode("idna")
    return b"\x03" + bytes([len(name)]) + name


async def socks5_reply_ok(recv_exact: RecvExact) -> bool:
    resp = await recv_exact(4)
    if resp[1] != 0x00:
        return False
    atyp = resp[3]
    if atyp == 1:
        await recv_exact(4 + 2)
    elif atyp == 4:
        await recv_exact(16 + 2)
    elif atyp == 3:
        ln = (await recv_exact(1))[0]
        await recv_exact(ln + 2)
    else:
        return False
    return True


def stream_io(reader, writer):
    """send/recv_exact for asyncio streams."""
    async def send(data: bytes) -> None:
        writer.write(data)
        await writer.drain()
    return send, reader.readexactly
