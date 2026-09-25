"""--serve-password: the rotating server only serves clients that know the password (#103)."""

import asyncio
import base64
import json

from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.options import RunOptions
from proxyscraper.server import ProxyPool, RotatingServer

from .fakes import http_forward_proxy, serve, target_server

PASSWORD = "s3cret:with-colon"


def basic(user, password):
    return base64.b64encode(f"{user}:{password}".encode()).decode()


def with_server(client, password=PASSWORD):
    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        result = CheckResult(f"http 127.0.0.1:{proxy_port}", "http", f"127.0.0.1:{proxy_port}", 100, "9.9.9.9",
                             https=True, country="DE")
        rotating = RotatingServer(ProxyPool([result]), port=0, timeout=3, password=password)
        await rotating.start()
        try:
            return await client(rotating.port, target_port)
        finally:
            await rotating.close()
            target_srv.close()
            proxy_srv.close()
    return asyncio.run(go())


async def http_get(port, target_port, auth=None, path="/ok"):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    extra = f"Proxy-Authorization: Basic {auth}\r\n" if auth else ""
    writer.write(f"GET http://127.0.0.1:{target_port}{path} HTTP/1.1\r\nHost: 127.0.0.1\r\n{extra}\r\n".encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(65536), 5)
    writer.close()
    return data


def test_http_needs_the_password():
    async def client(port, target_port):
        return [await http_get(port, target_port),
                await http_get(port, target_port, basic("country-de", "wrong")),
                await http_get(port, target_port, basic("country-de", PASSWORD))]

    missing, wrong, right = with_server(client)
    assert missing.startswith(b"HTTP/1.1 407") and b"Proxy-Authenticate: Basic" in missing
    assert wrong.startswith(b"HTTP/1.1 407")
    assert right.startswith(b"HTTP/1.1 200")  # the user name still selects country, the password lets it in


async def socks5(port, target_port, user=None, password=None):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    if user is None:
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        answer = await reader.readexactly(2)
        writer.close()
        return answer
    writer.write(b"\x05\x01\x02")
    await writer.drain()
    assert await reader.readexactly(2) == b"\x05\x02"
    writer.write(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
    await writer.drain()
    answer = await reader.readexactly(2)
    if answer == b"\x01\x00":
        writer.write(b"\x05\x01\x00\x01\x7f\x00\x00\x01" + target_port.to_bytes(2, "big"))
        await writer.drain()
        answer += await asyncio.wait_for(reader.readexactly(10), 5)
    writer.close()
    return answer


def test_socks5_needs_the_password():
    async def client(port, target_port):
        return [await socks5(port, target_port),
                await socks5(port, target_port, b"any", b"wrong"),
                await socks5(port, target_port, b"any", PASSWORD.encode())]

    no_auth, wrong, right = with_server(client)
    assert no_auth == b"\x05\xff"          # "no auth" isn't offered any more
    assert wrong == b"\x01\x01"            # login refused
    assert right[:2] == b"\x01\x00" and right[2:4] == b"\x05\x00"  # logged in, CONNECT succeeded


def test_status_needs_basic_auth():
    async def get(port, auth=None):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        extra = f"Authorization: Basic {auth}\r\n" if auth else ""
        writer.write(f"GET /__proxy-scraper/status HTTP/1.1\r\nHost: x\r\n{extra}\r\n".encode())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(1 << 20), 5)
        writer.close()
        return data

    async def client(port, target_port):
        return await get(port), await get(port, basic("any", PASSWORD))

    denied, allowed = with_server(client)
    assert denied.startswith(b"HTTP/1.1 401") and b"WWW-Authenticate: Basic" in denied
    assert allowed.startswith(b"HTTP/1.1 200") and json.loads(allowed.partition(b"\r\n\r\n")[2])["pool"]["total"] == 1


def test_without_a_password_nothing_changes():
    async def client(port, target_port):
        return await http_get(port, target_port)

    assert with_server(client, password="").startswith(b"HTTP/1.1 200")


def test_password_comes_from_the_environment_and_never_goes_to_argv(monkeypatch):
    monkeypatch.setenv("PROXY_SCRAPER_SERVE_PASSWORD", "from-env")
    opts = RunOptions.from_args(parse_args(["--serve"]))
    assert opts.serve_password == "from-env"
    assert "from-env" not in " ".join(opts.to_argv())  # the wizard saves argv to disk
    assert "from-env" not in repr(opts)
