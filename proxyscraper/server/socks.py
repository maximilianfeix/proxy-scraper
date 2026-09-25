"""SOCKS5 on the client side: greeting, optional authentication (RFC 1929) and accepting CONNECT."""

from __future__ import annotations

import socket
from typing import Tuple

SOCKS5_VERSION = b"\x05"
NO_AUTH, USER_PASS, NO_METHOD = 0x00, 0x02, 0xFF
CMD_CONNECT = 0x01
ATYP_IPV4, ATYP_DOMAIN, ATYP_IPV6 = 0x01, 0x03, 0x04


class Socks5Refused(Exception):
    """The client doesn't speak usable SOCKS5 or wants something other than CONNECT – the reply is already sent."""


def socks5_reply(code: int) -> bytes:
    """Reply to the CONNECT request. 0x00 = ok, 0x04 = host unreachable, 0x07 = command not supported."""
    return bytes([5, code, 0, ATYP_IPV4]) + b"\x00" * 6


async def socks5_accept(reader, writer) -> Tuple[str, int, str]:
    """After the first byte (0x05): negotiate methods, authenticate if needed, read CONNECT.

    -> (target host, target port, user name). The user name is not password protection – the server only
    listens on 127.0.0.1 – but carries wishes like "country-de" (see pool.Selection)."""
    count = (await reader.readexactly(1))[0]
    methods = await reader.readexactly(count)
    username = ""
    if USER_PASS in methods:
        writer.write(bytes([5, USER_PASS]))
        await writer.drain()
        await reader.readexactly(1)  # version of the sub-negotiation
        username = (await reader.readexactly((await reader.readexactly(1))[0])).decode("utf-8", "replace")
        await reader.readexactly((await reader.readexactly(1))[0])  # Passwort – egal
        writer.write(b"\x01\x00")
    elif NO_AUTH in methods:
        writer.write(bytes([5, NO_AUTH]))
    else:
        writer.write(bytes([5, NO_METHOD]))
        await writer.drain()
        raise Socks5Refused("no supported method")
    await writer.drain()

    version, command, _, atyp = await reader.readexactly(4)
    if atyp == ATYP_IPV4:
        host = socket.inet_ntoa(await reader.readexactly(4))
    elif atyp == ATYP_DOMAIN:
        host = (await reader.readexactly((await reader.readexactly(1))[0])).decode("idna")
    elif atyp == ATYP_IPV6:
        host = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
    else:
        host = ""
    port = int.from_bytes(await reader.readexactly(2), "big")
    if version != 5 or command != CMD_CONNECT or not host or not port:
        writer.write(socks5_reply(0x07))
        await writer.drain()
        raise Socks5Refused("CONNECT only")
    return host, port, username
