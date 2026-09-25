"""Echte, weiterleitende Mini-Proxys und ein Zielserver auf localhost – für Tests ohne Internet."""

import asyncio
import base64
import socket
import ssl
from pathlib import Path


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass  # Gegenseite hat aufgelegt – für einen Test-Proxy kein Fehler
    finally:
        writer.close()


async def target_server(reader, writer):
    """Zielseite: /ok -> 200, /weiter -> 302, alles andere -> 403 (wie eine Seite, die Proxys sperrt)."""
    head = await reader.readuntil(b"\r\n\r\n")
    path = head.split()[1]
    if path.endswith(b"/echo"):
        length = int(next((line.split(b":", 1)[1] for line in head.split(b"\r\n")
                           if line.lower().startswith(b"content-length:")), b"0"))
        if b"expect: 100-continue" in head.lower():
            writer.write(b"HTTP/1.1 100 Continue\r\n\r\n")  # wie ein echter Server: erst dann kommt der Body
            await writer.drain()
        body = await reader.readexactly(length) if length else b""
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
    elif path.endswith(b"/host-mit-port"):
        # 200 nur, wenn der Host-Header den (nicht standardmäßigen) Port enthält
        port = writer.get_extra_info("sockname")[1]
        ok = f"Host: 127.0.0.1:{port}\r\n".encode() in head
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n" if ok else
                     b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
    elif path.endswith(b"/ok"):
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    elif path.endswith(b"/weiter"):
        writer.write(b"HTTP/1.1 302 Found\r\nLocation: /ok\r\nContent-Length: 0\r\n\r\n")
    else:
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
    await writer.drain()
    writer.close()


async def http_forward_proxy(reader, writer):
    """HTTP-Proxy: absolute URLs weiterleiten und CONNECT tunneln."""
    await _http_forward(await reader.readuntil(b"\r\n\r\n"), reader, writer)


async def _http_forward(head, reader, writer):
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
    """SOCKS5-Proxy ohne Anmeldung, IPv4-Adressen und Hostnamen."""
    await reader.readexactly(3)
    writer.write(b"\x05\x00")
    await _socks5_connect(reader, writer)


async def _socks5_connect(reader, writer):
    head = await reader.readexactly(4)
    if head[3] == 1:
        host = socket.inet_ntoa(await reader.readexactly(4))
    else:
        host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
    port = int.from_bytes(await reader.readexactly(2), "big")
    up_reader, up_writer = await asyncio.open_connection(host, port)
    writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
    await writer.drain()
    await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))


async def serve(handler):
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


DATA = Path(__file__).parent / "data"


def tls_server_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(DATA / "localhost-cert.pem", DATA / "localhost-key.pem")
    return ctx


def tls_client_context() -> ssl.SSLContext:
    """Vertraut genau dem Test-Zertifikat – wie certifi einem echten Zertifikat vertrauen würde."""
    return ssl.create_default_context(cafile=str(DATA / "localhost-cert.pem"))


async def serve_tls(handler):
    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=tls_server_context())
    return server, server.sockets[0].getsockname()[1]


async def blackhole_proxy(reader, writer):
    """Nimmt CONNECT an, schluckt das erste Paket und legt ohne Antwort auf (wie im echten Test beobachtet)."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
    await writer.drain()
    await reader.read(65536)
    writer.close()


async def echo_server(reader, writer):
    """Spricht in mehreren Runden: jede Zeile kommt mit Präfix zurück, bis 'bye'."""
    while True:
        line = await reader.readline()
        if not line or line.strip() == b"bye":
            break
        writer.write(b"echo: " + line)
        await writer.drain()
    writer.close()


async def error_page_proxy(reader, writer):
    """Nimmt CONNECT an, antwortet im Tunnel aber mit einer HTTP-Fehlerseite statt mit TLS."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
    await writer.drain()
    await reader.read(65536)
    writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 9\r\n\r\nverboten\n")
    await writer.drain()
    writer.close()


async def tls_like_server(reader, writer):
    """Antwortet auf ein Paket, das wie ein TLS ClientHello beginnt, mit einem 'ServerHello'."""
    data = await reader.read(65536)
    if data[:1] == b"\x16":
        writer.write(b"\x16\x03\x03\x00\x04" + b"helo")
        await writer.drain()
    writer.close()


async def socks4_forward_proxy(reader, writer):
    """SOCKS4-Proxy: nur IPv4-Adressen, User-ID wird ignoriert."""
    request = await reader.readexactly(8)
    await reader.readuntil(b"\x00")  # User-ID
    port = int.from_bytes(request[2:4], "big")
    ip = socket.inet_ntoa(request[4:8])
    up_reader, up_writer = await asyncio.open_connection(ip, port)
    writer.write(b"\x00\x5a" + request[2:8])
    await writer.drain()
    await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))


async def forward_only_proxy(reader, writer):
    """HTTP-Proxy ohne CONNECT – nur klassische Anfragen mit absoluter URL (wie manche Port-80-Proxys)."""
    head = await reader.readuntil(b"\r\n\r\n")
    if head.startswith(b"CONNECT"):
        writer.write(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()
        return
    method, url, rest = head.split(b" ", 2)
    hostport, _, path = url.decode().split("://", 1)[1].partition("/")
    host, _, port = hostport.partition(":")
    up_reader, up_writer = await asyncio.open_connection(host, int(port or 80))
    up_writer.write(method + b" /" + path.encode() + b" " + rest)
    await up_writer.drain()
    await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))


async def silent_proxy(reader, writer):
    """Nimmt die Anfrage an und legt ohne Antwort auf."""
    await reader.readuntil(b"\r\n\r\n")
    writer.close()


async def weird_status_proxy(reader, writer):
    """Antwortet auf CONNECT mit "HTTP/1.1 2000" – enthält " 200", ist aber kein Erfolg."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 2000 Irgendwas\r\n\r\n")
    await writer.drain()
    await reader.read(65536)
    writer.close()


async def tls_record_server(reader, writer):
    """Antwortet erst, wenn ein TLS-Record vollständig angekommen ist (wie ein echter TLS-Server)."""
    header = await reader.readexactly(5)
    await reader.readexactly(int.from_bytes(header[3:5], "big"))
    writer.write(b"\x16\x03\x03\x00\x02ok")
    await writer.drain()
    writer.close()


# Zugangsdaten der Proxys mit Login – mit Zeichen, die in URLs kodiert werden müssen
USER, PASSWORD = "alice", "p@ss:wörd"


async def auth_http_forward_proxy(reader, writer):
    """HTTP-Proxy mit Pflicht-Login: ohne passenden Proxy-Authorization-Header gibt es 407."""
    head = await reader.readuntil(b"\r\n\r\n")
    token = base64.b64encode(f"{USER}:{PASSWORD}".encode())
    if b"\r\nProxy-Authorization: Basic " + token + b"\r\n" not in head:
        writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()
        return
    await _http_forward(head, reader, writer)


async def auth_socks5_forward_proxy(reader, writer):
    """SOCKS5-Proxy, der nur Benutzer/Passwort (RFC 1929) akzeptiert."""
    _, count = await reader.readexactly(2)
    methods = await reader.readexactly(count)
    if 0x02 not in methods:
        writer.write(b"\x05\xff")  # keine akzeptable Methode
        await writer.drain()
        writer.close()
        return
    writer.write(b"\x05\x02")
    await reader.readexactly(1)
    user = await reader.readexactly((await reader.readexactly(1))[0])
    password = await reader.readexactly((await reader.readexactly(1))[0])
    if (user.decode(), password.decode()) != (USER, PASSWORD):
        writer.write(b"\x01\x01")
        await writer.drain()
        writer.close()
        return
    writer.write(b"\x01\x00")
    await _socks5_connect(reader, writer)
