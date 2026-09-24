"""Checker gegen Fake-Proxys auf localhost – testet die Handshakes ohne Internet."""

import asyncio
import gc
import json
from contextlib import suppress

import pytest

from proxyscraper import checker as ck

JUDGE_REPLY = b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: keep-alive\r\n\r\n9.9.9.9\n"


async def _serve(handler):
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def http_proxy(reader, writer):
    head = await reader.readuntil(b"\r\n\r\n")
    if head.startswith(b"GET http://checkip.amazonaws.com/"):
        writer.write(JUDGE_REPLY)
    elif head.startswith(b"GET http://httpbin.org/headers"):
        body = json.dumps({"headers": {"Host": "httpbin.org", "Via": "1.1 squid"}}).encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
    else:
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
    await writer.drain()
    writer.close()


async def socks5_proxy(reader, writer):
    assert await reader.readexactly(3) == b"\x05\x01\x00"
    writer.write(b"\x05\x00")
    req = await reader.readexactly(10)
    assert req[:4] == b"\x05\x01\x00\x01"
    writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
    await reader.readuntil(b"\r\n\r\n")
    writer.write(JUDGE_REPLY)
    await writer.drain()
    writer.close()


async def socks4_reject(reader, writer):
    await reader.readexactly(9)
    writer.write(b"\x00\x5b" + b"\x00" * 6)  # 0x5B = abgelehnt
    await writer.drain()
    writer.close()


def run_check(handler, ptype, own_ip="1.1.1.1"):
    async def go():
        server, port = await _serve(handler)
        async with server:
            c = ck.Checker("3.3.3.3", {own_ip}, timeout=3, connect_timeout=2)
            result = await c.check(f"{ptype} 127.0.0.1:{port}")
            anonymity = await c.check_anonymity(ptype, f"127.0.0.1:{port}") if result else None
            return result, anonymity

    return asyncio.run(go())


def test_http_proxy_works_and_is_anonymous():
    result, anonymity = run_check(http_proxy, "http")
    assert result.exit_ip == "9.9.9.9" and result.ptype == "http"
    assert anonymity == "anonymous"  # Via-Header verrät den Proxy


def test_socks5_proxy_works_and_is_elite():
    result, anonymity = run_check(socks5_proxy, "socks5")
    assert result.exit_ip == "9.9.9.9"
    assert anonymity == "elite"


def test_socks4_rejection_is_not_working():
    result, _ = run_check(socks4_reject, "socks4")
    assert result is None


def test_transparent_proxy_revealing_real_ip_is_rejected():
    result, _ = run_check(http_proxy, "http", own_ip="9.9.9.9")
    assert result is None


def test_unreachable_proxy_is_cached():
    async def go():
        c = ck.Checker("3.3.3.3", set(), timeout=2, connect_timeout=1)
        # Port 1 auf localhost ist praktisch immer zu -> Connection refused
        assert await c.check("http 127.0.0.1:1") is None
        return c.unreachable

    assert "127.0.0.1:1" in asyncio.run(go())


@pytest.mark.parametrize("headers, expected", [
    ({"Host": "httpbin.org"}, "elite"),
    ({"X-Forwarded-For": "7.7.7.7"}, "anonymous"),
    ({"X-Forwarded-For": "5.5.5.5"}, "transparent"),
    ({"X-Real-Ip": "172.226.1.1"}, "transparent"),  # zweite eigene IP (Port-80-Umweg)
])
def test_classify_anonymity(headers, expected):
    own = {"5.5.5.5", "172.226.1.1"}
    assert ck.classify_anonymity(json.dumps({"headers": headers}).encode(), own) == expected


def test_wait_for_leaves_no_unretrieved_exception_on_cancel():
    """Strg+C genau in dem Moment, in dem der innere Connect scheitert (Python < 3.12)."""

    async def go():
        loop = asyncio.get_running_loop()
        errors = []
        loop.set_exception_handler(lambda _loop, context: errors.append(context["message"]))
        connect = loop.create_future()

        async def check():  # wie Checker._check: innerer Connect mit eigenem Timeout
            return await asyncio.wait_for(connect, 5)

        outer = asyncio.ensure_future(ck.wait_for(check(), 5))
        for _ in range(3):
            await asyncio.sleep(0)
        outer.cancel()
        # Ab Python 3.12 bricht wait_for den inneren Connect sofort mit ab – dann gibt es das
        # Zeitfenster nicht, und der Test prüft nur noch, dass nichts liegen bleibt.
        if not connect.done():
            connect.set_exception(ConnectionRefusedError())
        with suppress(BaseException):
            await outer
        for _ in range(3):
            await asyncio.sleep(0.01)
            gc.collect()
        return errors

    assert asyncio.run(go()) == []
