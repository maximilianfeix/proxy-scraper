"""Echte, weiterleitende Mini-Proxys und ein Zielserver auf localhost – für Tests ohne Internet."""

import asyncio
import socket


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()


async def target_server(reader, writer):
    """Zielseite: /ok -> 200, /weiter -> 302, alles andere -> 403 (wie eine Seite, die Proxys sperrt)."""
    head = await reader.readuntil(b"\r\n\r\n")
    path = head.split()[1]
    if path.endswith(b"/ok"):
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    elif path.endswith(b"/weiter"):
        writer.write(b"HTTP/1.1 302 Found\r\nLocation: /ok\r\nContent-Length: 0\r\n\r\n")
    else:
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
    await writer.drain()
    writer.close()


async def http_forward_proxy(reader, writer):
    """HTTP-Proxy: absolute URLs weiterleiten und CONNECT tunneln."""
    head = await reader.readuntil(b"\r\n\r\n")
    method, url, rest = head.split(b" ", 2)
    if method == b"CONNECT":
        host, port = url.decode().rsplit(":", 1)
        up_reader, up_writer = await asyncio.open_connection(host, int(port))
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
    else:
        hostport, _, path = url.decode().split("://", 1)[1].partition("/")
        host, _, port = hostport.partition(":")
        up_reader, up_writer = await asyncio.open_connection(host, int(port or 80))
        up_writer.write(method + b" /" + path.encode() + b" " + rest)
        await up_writer.drain()
    await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))


async def socks5_forward_proxy(reader, writer):
    """SOCKS5-Proxy ohne Anmeldung, IPv4-Adressen."""
    await reader.readexactly(3)
    writer.write(b"\x05\x00")
    request = await reader.readexactly(10)
    ip = socket.inet_ntoa(request[4:8])
    port = int.from_bytes(request[8:10], "big")
    up_reader, up_writer = await asyncio.open_connection(ip, port)
    writer.write(b"\x05\x00\x00\x01" + request[4:10])
    await writer.drain()
    await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))


async def serve(handler):
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]
