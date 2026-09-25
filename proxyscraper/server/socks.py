"""SOCKS5 auf der Client-Seite: Begrüßung, optionale Anmeldung (RFC 1929) und CONNECT entgegennehmen."""

from __future__ import annotations

import socket
from typing import Tuple

SOCKS5_VERSION = b"\x05"
NO_AUTH, USER_PASS, NO_METHOD = 0x00, 0x02, 0xFF
CMD_CONNECT = 0x01
ATYP_IPV4, ATYP_DOMAIN, ATYP_IPV6 = 0x01, 0x03, 0x04


class Socks5Refused(Exception):
    """Client spricht kein brauchbares SOCKS5 oder will etwas anderes als CONNECT – Antwort ist schon raus."""


def socks5_reply(code: int) -> bytes:
    """Antwort auf die CONNECT-Anfrage. 0x00 = ok, 0x04 = Host nicht erreichbar, 0x07 = Befehl nicht unterstützt."""
    return bytes([5, code, 0, ATYP_IPV4]) + b"\x00" * 6


async def socks5_accept(reader, writer) -> Tuple[str, int, str]:
    """Nach dem ersten Byte (0x05): Methoden aushandeln, ggf. Anmeldung, CONNECT lesen.

    -> (Zielhost, Zielport, Benutzername). Der Benutzername ist kein Passwort-Schutz – der Server lauscht
    nur auf 127.0.0.1 –, sondern trägt Wünsche wie "country-de" (siehe pool.Selection)."""
    count = (await reader.readexactly(1))[0]
    methods = await reader.readexactly(count)
    username = ""
    if USER_PASS in methods:
        writer.write(bytes([5, USER_PASS]))
        await writer.drain()
        await reader.readexactly(1)  # Version der Unterverhandlung
        username = (await reader.readexactly((await reader.readexactly(1))[0])).decode("utf-8", "replace")
        await reader.readexactly((await reader.readexactly(1))[0])  # Passwort – egal
        writer.write(b"\x01\x00")
    elif NO_AUTH in methods:
        writer.write(bytes([5, NO_AUTH]))
    else:
        writer.write(bytes([5, NO_METHOD]))
        await writer.drain()
        raise Socks5Refused("keine unterstützte Methode")
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
        raise Socks5Refused("nur CONNECT")
    return host, port, username
