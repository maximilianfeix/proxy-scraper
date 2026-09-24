"""Proxys mit Zugangsdaten: Parser, Handshakes, Checker, Proxy-Server und Ausgabe."""

import asyncio
import base64
from datetime import datetime

import pytest

from proxyscraper import checker as ck
from proxyscraper.checker import CheckResult
from proxyscraper.exporters import clash, proxychains
from proxyscraper.handshake import Endpoint, format_auth, parse_endpoint, socks4, with_proxy_auth
from proxyscraper.parsing import parse_proxy_line
from proxyscraper.server import ProxyPool, RotatingServer

from .fakes import PASSWORD, USER, auth_http_forward_proxy, auth_socks5_forward_proxy, serve, target_server

AUTH = format_auth(USER, PASSWORD)  # "alice:p%40ss%3Aw%C3%B6rd"


def test_endpoint_roundtrip_with_special_characters():
    assert AUTH == "alice:p%40ss%3Aw%C3%B6rd"
    assert parse_endpoint(f"{AUTH}@1.2.3.4:1080") == Endpoint("1.2.3.4", 1080, USER, PASSWORD)
    assert parse_endpoint("1.2.3.4:80") == Endpoint("1.2.3.4", 80)
    assert parse_proxy_line(f"socks5://{AUTH}@1.2.3.4:1080") == f"socks5 {AUTH}@1.2.3.4:1080"


def test_proxy_authorization_header():
    request = b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n"
    token = base64.b64encode(f"{USER}:{PASSWORD}".encode())
    out = with_proxy_auth(request, Endpoint("1.2.3.4", 80, USER, PASSWORD))
    assert out == request[:-2] + b"Proxy-Authorization: Basic " + token + b"\r\n\r\n"
    assert with_proxy_auth(request, Endpoint("1.2.3.4", 80)) == request  # ohne Login unverändert


def test_socks4_sends_the_user_id():
    sent = []

    async def send(data):
        sent.append(data)

    async def recv_exact(n):
        return b"\x00\x5a" + b"\x00" * (n - 2)

    ok = asyncio.run(socks4(send, recv_exact, Endpoint("1.2.3.4", 1080, "bob"), b"\x05\x06\x07\x08", 80))
    assert ok and sent == [b"\x04\x01\x00\x50\x05\x06\x07\x08bob\x00"]


def pooled(ptype, port, auth):
    proxy = f"{auth}@127.0.0.1:{port}" if auth else f"127.0.0.1:{port}"
    return CheckResult(f"{ptype} {proxy}", ptype, proxy, 100, "9.9.9.9", https=True)


def through_server(ptype, handler, auth, raw_request):
    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(handler)
        rotating = RotatingServer(ProxyPool([pooled(ptype, proxy_port, auth)]), port=0, timeout=3)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(raw_request(target_port))
            await writer.drain()
            data = b""
            while b"ok" not in data:
                chunk = await asyncio.wait_for(reader.read(65536), 5)
                if not chunk:
                    break
                data += chunk
            writer.close()
            return data
        finally:
            await rotating.close()
            for srv in (target_srv, proxy_srv):
                srv.close()

    return asyncio.run(go())


def plain(port):
    return f"GET http://127.0.0.1:{port}/ok HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode()


def tunnel(port):
    return (f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n"
            f"GET /ok HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n").encode()


@pytest.mark.parametrize("ptype, handler", [("http", auth_http_forward_proxy), ("socks5", auth_socks5_forward_proxy)])
@pytest.mark.parametrize("request_", [plain, tunnel])
def test_server_logs_in_to_upstream_proxies(ptype, handler, request_):
    assert b"200 OK" in through_server(ptype, handler, AUTH, request_)


@pytest.mark.parametrize("ptype, handler", [("http", auth_http_forward_proxy), ("socks5", auth_socks5_forward_proxy)])
@pytest.mark.parametrize("auth", ["", "alice:falsch"])
def test_missing_or_wrong_credentials_fail(ptype, handler, auth):
    assert b"502" in through_server(ptype, handler, auth, plain)


def test_checker_sends_credentials_to_http_proxies():
    async def judge_behind_login(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        token = base64.b64encode(f"{USER}:{PASSWORD}".encode())
        if b"Proxy-Authorization: Basic " + token in head:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n9.9.9.9\n")
        else:
            writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    async def go():
        srv, port = await serve(judge_behind_login)
        c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2)
        try:
            return (await c.check(f"http {AUTH}@127.0.0.1:{port}"), await c.check(f"http 127.0.0.1:{port}"))
        finally:
            srv.close()

    with_login, without = asyncio.run(go())
    assert with_login is not None and with_login.proxy.startswith(AUTH + "@")
    assert without is None


def test_exports_keep_credentials():
    r = CheckResult(f"socks5 {AUTH}@1.2.3.4:1080", "socks5", f"{AUTH}@1.2.3.4:1080", 90, "9.9.9.9", https=True)
    assert proxychains([r], datetime(2026, 9, 24)).splitlines()[-1] == f"socks5 1.2.3.4 1080 {USER} {PASSWORD}"
    text = clash([r], datetime(2026, 9, 24))
    assert '    server: "1.2.3.4"\n    port: 1080' in text
    assert f'    username: "{USER}"\n    password: "p@ss:w\\u00f6rd"' in text


def test_proxychains_skips_credentials_it_cannot_express():
    # proxychains trennt an Leerzeichen – so ein Passwort lässt sich dort nicht eintragen
    auth = format_auth("bob", "mit leerzeichen")
    r = CheckResult(f"socks5 {auth}@1.2.3.4:1080", "socks5", f"{auth}@1.2.3.4:1080", 90, "9.9.9.9", https=True)
    assert "1.2.3.4" not in proxychains([r], datetime(2026, 9, 24))


def test_terminal_masks_passwords():
    from proxyscraper.ui.widgets import shown_proxy
    assert shown_proxy(f"{AUTH}@1.2.3.4:1080") == "alice:•••@1.2.3.4:1080"
    assert shown_proxy("1.2.3.4:1080") == "1.2.3.4:1080"
