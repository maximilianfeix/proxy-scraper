"""Proxy server fixes from the package review (#82)."""

import asyncio

from proxyscraper.checker import CheckResult
from proxyscraper.server import ProxyPool, RotatingServer
from proxyscraper.server import core as server_core
from proxyscraper.server.upstream import TargetError, _handshake

from .fakes import http_forward_proxy, serve, target_server


async def gateway_error_proxy(reader, writer):
    """A working proxy whose target is down: answers every CONNECT with 502."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
    await writer.drain()
    writer.close()


def entry(port):
    return CheckResult(f"http 127.0.0.1:{port}", "http", f"127.0.0.1:{port}", 100, "9.9.9.9", https=True)


async def connect(server_port, target):
    reader, writer = await asyncio.open_connection("127.0.0.1", server_port)
    writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    await writer.drain()
    head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    writer.close()
    return head.split(b"\r\n", 1)[0]


def test_a_dead_target_does_not_disable_the_pool():
    async def go():
        proxies = [await serve(gateway_error_proxy) for _ in range(3)]
        rotating = RotatingServer(ProxyPool([entry(port) for _, port in proxies]), port=0, timeout=2)
        await rotating.start()
        try:
            answers = [await connect(rotating.port, "dead.invalid:443") for _ in range(4)]
            return answers, rotating.pool
        finally:
            await rotating.close()
            for srv, _ in proxies:
                srv.close()

    answers, pool = asyncio.run(go())
    assert all(b"502" in a for a in answers)          # the client still hears that it didn't work
    assert len(pool.usable) == 3                      # but nobody was blamed for the dead target
    assert all(e.fail == 0 for e in pool.entries)


def test_a_proxy_that_cant_reach_a_working_target_is_blamed():
    async def go():
        target_srv, target_port = await serve(target_server)
        bad_srv, bad_port = await serve(gateway_error_proxy)
        good_srv, good_port = await serve(http_forward_proxy)
        bad, good = entry(bad_port), entry(good_port)
        good = CheckResult(good.key, good.ptype, good.proxy, 500, good.exit_ip, https=True)  # bad one is faster
        pool = ProxyPool([bad, good], strategy="fastest")
        rotating = RotatingServer(pool, port=0, timeout=2)
        await rotating.start()
        try:
            answer = await connect(rotating.port, f"127.0.0.1:{target_port}")
            return answer, {e.result.proxy: e.fail for e in pool.entries}, bad.proxy, good.proxy
        finally:
            await rotating.close()
            for srv in (target_srv, bad_srv, good_srv):
                srv.close()

    answer, fails, bad, good = asyncio.run(go())
    assert b"200" in answer
    assert fails == {bad: 1, good: 0}


class Recorder:
    def __init__(self, reply=b"HTTP/1.1 200 Connection established\r\n\r\n"):
        self.sent, self.reply = b"", reply

    def write(self, data):
        self.sent += data

    async def drain(self):
        pass


def test_ipv6_targets_are_bracketed_in_connect():
    async def go():
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 200 Connection established\r\n\r\n")
        writer = Recorder()
        await _handshake("http", "1.2.3.4:8080", reader, writer, "2001:db8::1", 443)
        return writer.sent

    sent = asyncio.run(go())
    assert sent.startswith(b"CONNECT [2001:db8::1]:443 HTTP/1.1\r\nHost: [2001:db8::1]:443\r\n")


def test_socks4_cant_do_ipv6_and_says_so():
    async def go():
        try:
            await _handshake("socks4", "1.2.3.4:1080", asyncio.StreamReader(), Recorder(), "2001:db8::1", 443)
        except TargetError:
            return True
        return False

    assert asyncio.run(go())


def test_client_leaving_mid_body_is_not_an_error():
    errors = []

    async def go():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _loop, ctx: errors.append(ctx))
        rotating = RotatingServer(ProxyPool([entry(9)]), port=0, timeout=2)
        await rotating.start()
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(b"POST http://example.org/ HTTP/1.1\r\nHost: example.org\r\nContent-Length: 1000\r\n\r\n"
                         + b"x" * 10)
            await writer.drain()
            writer.close()  # gone before the body is complete
            await asyncio.sleep(0.3)
            return rotating.stats.active
        finally:
            await rotating.close()

    assert asyncio.run(go()) == 0 and errors == []


def test_a_slow_client_hello_keeps_what_already_arrived(monkeypatch):
    monkeypatch.setattr(server_core, "FIRST_CHUNK_WAIT", 0.1)

    async def go():
        reader = asyncio.StreamReader()
        # a TLS record header announcing 100 bytes, but only 20 of them arrive in time
        reader.feed_data(b"\x16\x03\x01\x00\x64" + b"a" * 20)
        rotating = RotatingServer(ProxyPool([entry(9)]), port=0)
        return await rotating._first_client_chunk(reader)

    assert asyncio.run(go()) == b"\x16\x03\x01\x00\x64" + b"a" * 20
