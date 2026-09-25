"""Verbindungsaufbau durch HTTP-, SOCKS4- und SOCKS5-Proxys – für Checker und Proxy-Server.

Proxys mit Zugangsdaten stehen als "user:pass@ip:port" im Schlüssel, Benutzer und Passwort
URL-kodiert (sonst würden ":" oder "@" im Passwort alles durcheinanderbringen).

Die Funktionen bekommen send/recv_exact statt eines Streams, weil der HTTPS-Test mit
nackten Sockets arbeitet und der Rest mit asyncio-Streams.
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
    """'user:pass@1.2.3.4:1080' oder '1.2.3.4:1080' -> Endpoint."""
    auth, _, address = proxy.rpartition("@")
    host, _, port = address.rpartition(":")
    user, _, password = auth.partition(":")
    return Endpoint(host, int(port), unquote(user), unquote(password))


def format_auth(user: str, password: str) -> str:
    """Benutzer und Passwort so kodieren, wie sie im Schlüssel stehen ('' ohne Benutzer)."""
    if not user:
        return ""
    return quote(user, safe="") + (":" + quote(password, safe="") if password else "")


def proxy_authorization(ep: Endpoint) -> bytes:
    """Header-Zeile für HTTP-Proxys (inkl. \\r\\n), leer ohne Zugangsdaten."""
    if not ep.has_auth:
        return b""
    token = base64.b64encode(f"{ep.user}:{ep.password}".encode()).decode()
    return f"Proxy-Authorization: Basic {token}\r\n".encode()


def with_proxy_auth(request: bytes, ep: Endpoint) -> bytes:
    """Hängt Proxy-Authorization an den Kopf einer fertigen HTTP-Anfrage (endet auf \\r\\n\\r\\n)."""
    header = proxy_authorization(ep)
    return request[:-2] + header + b"\r\n" if header else request


async def socks4(send: Send, recv_exact: RecvExact, ep: Endpoint, ip_bytes: bytes, port: int) -> bool:
    """SOCKS4 CONNECT; der Benutzername landet im User-ID-Feld (ein Passwort kennt SOCKS4 nicht)."""
    await send(b"\x04\x01" + port.to_bytes(2, "big") + ip_bytes + ep.user.encode()[:255] + b"\x00")
    return (await recv_exact(8))[1] == 0x5A


async def socks5(send: Send, recv_exact: RecvExact, ep: Endpoint, address: bytes, port: int) -> bool:
    """SOCKS5 CONNECT zu address (ATYP + Adresse, siehe socks5_ipv4/socks5_domain)."""
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
            return False  # Login abgelehnt
    elif reply[1] != SOCKS5_NO_AUTH:
        return False
    await send(b"\x05\x01\x00" + address + port.to_bytes(2, "big"))
    return await socks5_reply_ok(recv_exact)


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
    """send/recv_exact für asyncio-Streams."""
    async def send(data: bytes) -> None:
        writer.write(data)
        await writer.drain()
    return send, reader.readexactly
