"""Checker against fake proxies on localhost – tests the handshakes without internet."""

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


def confirm_reply(headers=None, origin="9.9.9.9") -> bytes:
    body = json.dumps({"origin": origin, "headers": headers or {"Host": "httpbin.org"}}).encode()
    return b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body


async def http_proxy(reader, writer):
    head = await reader.readuntil(b"\r\n\r\n")
    if head.startswith(b"GET http://checkip.amazonaws.com/"):
        writer.write(JUDGE_REPLY)
    elif head.startswith(b"GET http://httpbin.org/get"):
        writer.write(confirm_reply({"Host": "httpbin.org", "Via": "1.1 squid"}))
    else:
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
    await writer.drain()
    writer.close()


async def honeypot(reader, writer):
    """As observed: answers the check request with 200 + IP, everything else with 400."""
    head = await reader.readuntil(b"\r\n\r\n")
    if head.startswith(b"GET http://checkip.amazonaws.com/ "):
        writer.write(b"HTTP/1.1 200 OK\r\nServer: lighttpd/1.4.53\r\nContent-Length: 8\r\n\r\n9.9.9.9\n")
    else:
        writer.write(b"HTTP/1.1 400 Bad Request\r\nServer: NSC/0.6.4 (JVM)\r\nContent-Length: 0\r\n\r\n")
    await writer.drain()
    writer.close()


async def socks5_proxy(reader, writer):
    assert await reader.readexactly(3) == b"\x05\x01\x00"
    writer.write(b"\x05\x00")
    req = await reader.readexactly(10)
    assert req[:4] == b"\x05\x01\x00\x01"
    writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
    head = await reader.readuntil(b"\r\n\r\n")
    writer.write(confirm_reply() if b"Host: httpbin.org" in head else JUDGE_REPLY)
    await writer.drain()
    writer.close()


async def socks4_reject(reader, writer):
    await reader.readexactly(9)
    writer.write(b"\x00\x5b" + b"\x00" * 6)  # 0x5B = abgelehnt
    await writer.drain()
    writer.close()


def run_check(handler, ptype, own_ip="1.1.1.1", confirm_ip="4.4.4.4"):
    async def go():
        server, port = await _serve(handler)
        async with server:
            c = ck.Checker("3.3.3.3", {own_ip}, timeout=3, connect_timeout=2, confirm_ip=confirm_ip)
            result = await c.check(f"{ptype} 127.0.0.1:{port}")
            confirmed = await c.confirm(result) if result else None
            return result, confirmed

    return asyncio.run(go())


def test_http_proxy_works_and_is_anonymous():
    result, confirmed = run_check(http_proxy, "http")
    assert result.exit_ip == "9.9.9.9" and result.ptype == "http"
    assert confirmed and result.anonymity == "anonymous"  # the Via header gives the proxy away


def test_socks5_proxy_works_and_is_elite():
    result, confirmed = run_check(socks5_proxy, "socks5")
    assert result.exit_ip == "9.9.9.9"
    assert confirmed and result.anonymity == "elite"


def test_honeypot_passes_first_check_but_not_confirmation():
    result, confirmed = run_check(honeypot, "http")
    assert result is not None     # the first check alone falls for it …
    assert confirmed is False     # … the confirmation doesn't


def test_without_confirm_target_everything_is_confirmed():
    result, confirmed = run_check(honeypot, "http", confirm_ip=None)
    assert confirmed is True and result.anonymity == ""


def test_socks4_rejection_is_not_working():
    result, _ = run_check(socks4_reject, "socks4")
    assert result is None


def test_transparent_proxy_revealing_real_ip_is_rejected():
    result, _ = run_check(http_proxy, "http", own_ip="9.9.9.9")
    assert result is None


def test_unreachable_proxy_is_cached():
    async def go():
        c = ck.Checker("3.3.3.3", set(), timeout=2, connect_timeout=1)
        # port 1 on localhost is practically always closed -> connection refused
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
    """Ctrl+C exactly at the moment the inner connect fails (Python < 3.12)."""

    async def go():
        loop = asyncio.get_running_loop()
        errors = []
        loop.set_exception_handler(lambda _loop, context: errors.append(context["message"]))
        connect = loop.create_future()

        async def check():  # like Checker._check: inner connect with its own timeout
            return await asyncio.wait_for(connect, 5)

        outer = asyncio.ensure_future(ck.wait_for(check(), 5))
        for _ in range(3):
            await asyncio.sleep(0)
        outer.cancel()
        # from Python 3.12 on wait_for cancels the inner connect right away – then that time window
        # doesn't exist, and the test only checks that nothing is left behind.
        if not connect.done():
            connect.set_exception(ConnectionRefusedError())
        with suppress(BaseException):
            await outer
        for _ in range(3):
            await asyncio.sleep(0.01)
            gc.collect()
        return errors

    assert asyncio.run(go()) == []


@pytest.mark.parametrize("body, expected", [
    (json.dumps({"origin": "7.7.7.7", "headers": {}}).encode(), "elite"),
    (json.dumps({"origin": "5.5.5.5, 7.7.7.7", "headers": {"Via": "x"}}).encode(), "transparent"),
    (json.dumps({"origin": "8.8.8.8", "headers": {}}).encode(), None),       # a different exit IP than before
    (json.dumps({"origin": "not an ip", "headers": {}}).encode(), None),
    (json.dumps({"origin": "7.7.7.7", "headers": [1]}).encode(), None),     # must not crash
    (json.dumps({"origin": "7.7.7.7", "headers": "x"}).encode(), None),
    (json.dumps({"origin": "7.7.7.7"}).encode(), None),                     # not an httpbin response
    (json.dumps(["nope", "objekt"]).encode(), None),
    (b"<html>400 Bad Request</html>", None),
    (b"9.9.9.9", None),
])
def test_classify_confirmation(body, expected):
    assert ck.classify_confirmation(body, {"5.5.5.5"}, exit_ip="7.7.7.7") == expected


def test_confirm_survives_malformed_headers():
    async def weird(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        if head.startswith(b"GET http://checkip.amazonaws.com/ "):
            writer.write(JUDGE_REPLY)
        else:
            body = b'{"origin": "9.9.9.9", "headers": [1]}'
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
        await writer.drain()
        writer.close()

    result, confirmed = run_check(weird, "http")
    assert result is not None and confirmed is False


def test_confirm_reads_only_a_bounded_amount():
    """A proxy that sends megabytes must not eat memory with 2000 parallel checks."""
    sent = []

    async def huge(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        if head.startswith(b"GET http://checkip.amazonaws.com/ "):
            writer.write(JUDGE_REPLY)
        else:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 50000000\r\n\r\n")
            try:
                for _ in range(200):  # offer up to 12 MB
                    writer.write(b"x" * 65536)
                    await writer.drain()
                    sent.append(1)
            except (ConnectionError, OSError):
                pass
        writer.close()

    result, confirmed = run_check(huge, "http")
    assert result is not None and confirmed is False
    assert len(sent) < 200  # the connection was closed before


@pytest.mark.parametrize("reply, expected", [
    (confirm_reply(), True),
    (b"HTTP/1.1 301 Moved Permanently\r\nLocation: https://httpbin.org/get\r\nContent-Length: 0\r\n\r\n", False),
    (b"HTTP/1.1 200 OK\r\nContent-Length: 30\r\n\r\n<html>WLAN-Anmeldung</html>  ", False),
])
def test_probe_confirm_target(reply, expected):
    async def target(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        assert head.startswith(b"GET /get HTTP/1.1\r\nHost: httpbin.org")  # the same request as the confirmation
        writer.write(reply)
        await writer.drain()
        writer.close()

    async def go():
        server, port = await _serve(target)
        async with server:
            return await ck.probe_confirm_target("127.0.0.1", timeout=3, port=port)

    assert asyncio.run(go()) is expected


def test_confirmation_keeps_normal_connect_timeout():
    """With --max-latency only the timeout of the basic check shrinks, not that of the confirmation."""
    c = ck.Checker("3.3.3.3", set(), timeout=1.0, connect_timeout=1.0, detail_timeout=8.0, detail_connect_timeout=4.0)
    assert (c.connect_timeout, c.detail_connect_timeout) == (1.0, 4.0)


def test_detail_connection_failures_dont_mark_proxy_unreachable():
    async def go():
        c = ck.Checker("3.3.3.3", set(), timeout=2, connect_timeout=1)
        # Linux/macOS refuse right away, Windows waits for the timeout – both mean "unreachable"
        with pytest.raises((OSError, asyncio.TimeoutError)):
            await c._connect("127.0.0.1:1", detail=True)
        return c.unreachable

    assert asyncio.run(go()) == set()


@pytest.mark.parametrize("exit_ip", [b"127.0.0.1", b"10.0.0.5", b"192.168.1.1", b"0.0.0.0", b"100.64.1.1"])
def test_non_public_exit_ip_is_rejected(exit_ip):
    async def proxy_claiming(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        body = exit_ip + b"\n"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
        await writer.drain()
        writer.close()

    result, _ = run_check(proxy_claiming, "http")
    assert result is None
