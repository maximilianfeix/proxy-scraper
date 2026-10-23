"""Which requests the rotating server may send to a second proxy after the first one might already have
passed them on: only safe methods (RFC 9110 9.2.1) – a POST must never run twice on the target."""

import asyncio

import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.server import ProxyPool, RotatingServer

from .fakes import _http_forward, handlers_done, http_forward_proxy, serve, target_server


class OrderedPool(ProxyPool):
    def pick(self, exclude, tls=False, **_):
        return next((e for e in self.usable if e.result.key not in exclude), None)


def result(port):
    return CheckResult(f"http 127.0.0.1:{port}", "http", f"127.0.0.1:{port}", 100, "9.9.9.9", https=True)


def processing_then_dropping_proxy(effects):
    """Reads the whole request (head and Content-Length body), "executes" it – a side effect on the target –
    and then loses the connection before any response goes back."""
    async def handler(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        length = next((int(line.split(b":", 1)[1]) for line in head.split(b"\r\n")
                       if line.lower().startswith(b"content-length:")), 0)
        if length:
            await reader.readexactly(length)
        if head.startswith(b"CONNECT"):
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            effects.append(await reader.read(65536))
        else:
            effects.append(head.split(b" ", 1)[0])
        writer.close()
    return handler


def counting_forward_proxy(effects):
    """A working proxy that records every request it forwards."""
    async def handler(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        if not head.startswith(b"CONNECT"):
            effects.append(head.split(b" ", 1)[0])
        await _http_forward(head, reader, writer)
    return handler


async def read_all(reader):
    answer = b""
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(65536), 5)
        except ConnectionError:
            break
        if not chunk:
            break
        answer += chunk
    return answer


def run(request, effects_first, effects_second):
    async def go():
        target_srv, target_port = await serve(target_server)
        first_srv, first_port = await serve(processing_then_dropping_proxy(effects_first))
        second_srv, second_port = await serve(counting_forward_proxy(effects_second))
        pool = OrderedPool([result(first_port), result(second_port)])
        rotating = RotatingServer(pool, port=0, timeout=2)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(request(target_port))
            await writer.drain()
            answer = await read_all(reader)
            writer.close()
            await handlers_done(rotating)
            return answer, pool
        finally:
            await rotating.close()
            for srv in (target_srv, first_srv, second_srv):
                srv.close()

    return asyncio.run(go())


def http_request(method, body=b""):
    def build(target_port):
        return (f"{method} http://127.0.0.1:{target_port}/echo HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n"
                f"Content-Length: {len(body)}\r\n\r\n").encode() + body
    return build


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
def test_unsafe_request_is_not_sent_twice_when_the_response_is_lost(method):
    first, second = [], []
    answer, pool = run(http_request(method, b"pay=10"), first, second)
    assert first == [method.encode()] and second == []          # exactly one execution
    assert answer.startswith(b"HTTP/1.1 502")
    assert b"X-Proxy-Scraper: no-retry-after-send" in answer   # not "no-proxy-answered": it may have arrived
    assert pool.entries[0].fail == 1 and pool.entries[1].ok == 0 and pool.entries[1].fail == 0


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_request_still_fails_over(method):
    first, second = [], []
    answer, pool = run(http_request(method), first, second)
    assert first == [method.encode()] and second == [method.encode()]
    assert answer.startswith(b"HTTP/1.1 200")
    assert (pool.entries[0].fail, pool.entries[1].ok) == (1, 1)


def test_post_still_fails_over_when_the_first_proxy_is_unreachable():
    """Nothing was sent when the connection to the proxy fails – the next one may get the POST."""
    async def go():
        target_srv, target_port = await serve(target_server)
        good_srv, good_port = await serve(http_forward_proxy)
        pool = OrderedPool([result(1), result(good_port)])  # port 1: connection refused
        rotating = RotatingServer(pool, port=0, timeout=2)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(http_request("POST", b"daten")(target_port))
            await writer.drain()
            answer = await read_all(reader)
            writer.close()
            await handlers_done(rotating)
            return answer, pool
        finally:
            await rotating.close()
            target_srv.close()
            good_srv.close()

    answer, pool = asyncio.run(go())
    assert answer.startswith(b"HTTP/1.1 200") and answer.endswith(b"daten")
    assert (pool.entries[0].fail, pool.entries[1].ok) == (1, 1)


def tunnel(first_packet):
    def build(target_port):
        return f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\n\r\n".encode() + first_packet
    return build


def test_plain_post_inside_a_tunnel_is_not_replayed():
    """Plain HTTP through CONNECT: the first packet is a POST – after a possible send it doesn't go out again."""
    first, second = [], []
    packet = b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\nhi"
    answer, _ = run(tunnel(packet), first, second)
    assert first == [packet] and second == []
    assert answer.count(b"200 Connection established") == 1 and b"200 OK" not in answer


def test_plain_get_inside_a_tunnel_still_fails_over():
    first, second = [], []
    packet = b"GET /ok HTTP/1.1\r\nHost: x\r\n\r\n"
    answer, _ = run(tunnel(packet), first, second)
    assert first == [packet]
    assert answer.endswith(b"ok") and b"HTTP/1.1 200 OK" in answer

