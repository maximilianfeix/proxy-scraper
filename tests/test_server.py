import asyncio

import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.server import (
    DISABLE_AFTER,
    ProxyPool,
    RotatingServer,
    origin_request,
    parse_request_head,
    plausible_answer,
)

from .fakes import (
    blackhole_proxy,
    echo_server,
    error_page_proxy,
    forward_only_proxy,
    http_forward_proxy,
    serve,
    silent_proxy,
    socks4_forward_proxy,
    socks5_forward_proxy,
    target_server,
    tls_like_server,
    tls_record_server,
    weird_status_proxy,
)


def result(ptype, port, latency=100):
    return CheckResult(f"{ptype} 127.0.0.1:{port}", ptype, f"127.0.0.1:{port}", latency, "9.9.9.9")


class OrderedPool(ProxyPool):
    """Takes the proxies in a fixed order – makes failure tests independent of chance."""

    def pick(self, exclude, tls=False, **_):
        return next((e for e in self.usable if e.result.key not in exclude), None)


async def request_via(server_port: int, raw: bytes) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", server_port)
    writer.write(raw)
    await writer.drain()
    data = await asyncio.wait_for(reader.read(65536), 5)
    writer.close()
    return data


def run_server(upstreams, client_request, pool_cls=OrderedPool):
    """Starts the target server, upstream proxies and the rotating server; sends a client request."""
    async def go():
        target_srv, target_port = await serve(target_server)
        servers, results = [target_srv], []
        for kind, handler in upstreams:
            if handler is None:  # toter Proxy
                results.append(result(kind, 1))
                continue
            srv, port = await serve(handler)
            servers.append(srv)
            results.append(result(kind, port))
        pool = pool_cls(results)
        rotating = RotatingServer(pool, port=0, timeout=3)
        await rotating.start()
        try:
            answer = await client_request(rotating.port, target_port)
        finally:
            await rotating.close()
            for srv in servers:
                srv.close()
        return answer, pool, rotating.stats

    return asyncio.run(go())


async def plain_get(server_port, target_port):
    raw = (f"GET http://127.0.0.1:{target_port}/ok HTTP/1.1\r\n"
           f"Host: 127.0.0.1:{target_port}\r\nProxy-Connection: keep-alive\r\n\r\n")
    return await request_via(server_port, raw.encode())


async def connect_then_get(server_port, target_port):
    reader, writer = await asyncio.open_connection("127.0.0.1", server_port)
    writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n\r\n".encode())
    await writer.drain()
    established = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    writer.write(b"GET /ok HTTP/1.1\r\nHost: x\r\n\r\n")
    await writer.drain()
    answer = await asyncio.wait_for(reader.read(65536), 5)
    writer.close()
    return established + answer


@pytest.mark.parametrize("kind, handler", [("http", http_forward_proxy), ("socks5", socks5_forward_proxy)])
def test_plain_http_through_pool(kind, handler):
    answer, _pool, stats = run_server([(kind, handler)], plain_get)
    assert answer.startswith(b"HTTP/1.1 200") and answer.endswith(b"ok")
    assert (stats.requests, stats.ok, stats.failed) == (1, 1, 0)


@pytest.mark.parametrize("kind, handler", [("http", http_forward_proxy), ("socks5", socks5_forward_proxy)])
def test_connect_tunnel_through_pool(kind, handler):
    answer, _pool, stats = run_server([(kind, handler)], connect_then_get)
    assert answer.startswith(b"HTTP/1.1 200 Connection established")
    assert b"HTTP/1.1 200 OK" in answer and answer.endswith(b"ok")
    assert stats.bytes_down > 0


def test_failover_to_next_proxy():
    answer, pool, stats = run_server([("socks5", None), ("http", http_forward_proxy)], plain_get)
    assert answer.startswith(b"HTTP/1.1 200")
    dead, good = pool.entries[0], pool.entries[1]
    assert (dead.fail, good.ok) == (1, 1)
    assert stats.recent[-1].attempts == 2


def test_all_proxies_dead_gives_502():
    answer, _pool, stats = run_server([("http", None), ("socks5", None)], plain_get)
    assert answer.startswith(b"HTTP/1.1 502")
    assert (stats.ok, stats.failed) == (0, 1)


def test_bad_request_gives_400():
    async def garbage(server_port, target_port):
        return await request_via(server_port, b"GET /relativ HTTP/1.1\r\nHost: x\r\n\r\n")

    answer, _, _ = run_server([("http", http_forward_proxy)], garbage)
    assert answer.startswith(b"HTTP/1.1 400")


def test_pool_disables_after_repeated_failures():
    pool = ProxyPool([result("http", 1)])
    entry = pool.entries[0]
    for _ in range(DISABLE_AFTER - 1):
        pool.report(entry, False)
    pool.report(entry, True)             # a success resets the streak
    assert not entry.disabled
    for _ in range(DISABLE_AFTER):
        pool.report(entry, False)
    assert entry.disabled and pool.pick(set()) is None


def test_pool_prefers_fast_proxies():
    import random

    pool = ProxyPool([result("http", 1, latency=100), result("http", 2, latency=5000)], rng=random.Random(1))
    picks = [pool.pick(set()).result.latency for _ in range(500)]
    assert picks.count(100) > picks.count(5000) * 5


def test_parse_request_head():
    assert parse_request_head(b"CONNECT example.org:443 HTTP/1.1\r\nHost: example.org:443\r\n\r\n")[:3] == \
        ("CONNECT", "example.org", 443)
    method, host, port, path, _headers = parse_request_head(
        b"GET http://example.org/a?b=1 HTTP/1.1\r\nHost: example.org\r\nProxy-Connection: keep-alive\r\n\r\n")
    assert (method, host, port, path) == ("GET", "example.org", 80, b"/a?b=1")
    with pytest.raises(ValueError):
        parse_request_head(b"GET /relativ HTTP/1.1\r\n\r\n")


def test_origin_request_strips_proxy_headers():
    raw = origin_request("GET", b"/a", "example.org", 80,
                         [(b"Host", b"example.org"), (b"Proxy-Connection", b"keep-alive"), (b"Accept", b"*/*")])
    assert raw == b"GET /a HTTP/1.1\r\nHost: example.org\r\nAccept: */*\r\nConnection: close\r\n\r\n"


def test_tunnel_without_answer_is_retried_transparently():
    """The proxy confirms CONNECT but delivers nothing – the client doesn't notice the switch."""
    answer, pool, stats = run_server([("http", blackhole_proxy), ("http", http_forward_proxy)], connect_then_get)
    assert answer.startswith(b"HTTP/1.1 200 Connection established")
    assert answer.count(b"HTTP/1.1 200 Connection established") == 1  # only once to the client
    assert b"HTTP/1.1 200 OK" in answer and answer.endswith(b"ok")
    blackhole, good = pool.entries
    assert (blackhole.fail, good.ok) == (1, 1)
    assert stats.recent[-1].attempts == 2 and stats.ok == 1


@pytest.mark.parametrize("kind, handler", [("http", http_forward_proxy), ("socks5", socks5_forward_proxy)])
def test_tunnel_carries_a_whole_conversation(kind, handler):
    """Like TLS: several rounds back and forth, not just the first packet."""
    async def go():
        echo_srv, echo_port = await serve(echo_server)
        proxy_srv, proxy_port = await serve(handler)
        rotating = RotatingServer(OrderedPool([result(kind, proxy_port)]), port=0, timeout=3)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            await reader.readuntil(b"\r\n\r\n")
            answers = []
            for word in (b"eins", b"two", b"drei"):
                writer.write(word + b"\n")
                await writer.drain()
                answers.append(await asyncio.wait_for(reader.readline(), 3))
            writer.write(b"bye\n")
            writer.close()
            return answers
        finally:
            await rotating.close()
            echo_srv.close()
            proxy_srv.close()

    assert asyncio.run(go()) == [b"echo: eins\n", b"echo: two\n", b"echo: drei\n"]


def test_non_tls_answer_to_tls_is_retried():
    """The proxy returns an HTTP error page instead of TLS in the tunnel – next proxy, the client notices nothing."""
    async def go():
        tls_srv, tls_port = await serve(tls_like_server)
        bad_srv, bad_port = await serve(error_page_proxy)
        good_srv, good_port = await serve(http_forward_proxy)
        pool = OrderedPool([result("http", bad_port), result("http", good_port)])
        rotating = RotatingServer(pool, port=0, timeout=3)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(f"CONNECT 127.0.0.1:{tls_port} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"\x16\x03\x01\x00\x05hello")  # looks like a ClientHello
            await writer.drain()
            answer = await asyncio.wait_for(reader.read(100), 3)
            writer.close()
            return answer, pool
        finally:
            await rotating.close()
            for srv in (tls_srv, bad_srv, good_srv):
                srv.close()

    answer, pool = asyncio.run(go())
    assert answer.startswith(b"\x16\x03\x03")
    assert (pool.entries[0].fail, pool.entries[1].ok) == (1, 1)


@pytest.mark.parametrize("out, answer, expected", [
    (b"\x16\x03\x01...", b"\x16\x03\x03...", True),
    (b"\x16\x03\x01...", b"\x15\x03\x03\x00\x02", True),       # a TLS alert is real TLS too
    (b"\x16\x03\x01...", b"HTTP/1.1 403 Forbidden", False),
    (b"GET / HTTP/1.1", b"HTTP/1.1 200 OK", True),
    (b"", b"SSH-2.0-OpenSSH", True),                            # Server spricht zuerst
    (b"GET / HTTP/1.1", b"HTTP/1.1 407 Proxy Authentication Required", False),  # Proxy will Login
    (b"GET / HTTP/1.1", b"HTTP/1.1 4070", True),
])
def test_plausible_answer(out, answer, expected):
    assert plausible_answer(out, answer) is expected


def test_tls_prefers_proxies_that_passed_the_https_test():
    import random

    good, mitm = result("http", 1), result("http", 2, latency=10)
    good.https, mitm.https = True, False
    pool = ProxyPool([good, mitm], rng=random.Random(3))
    assert {pool.pick(set(), tls=True).result.key for _ in range(50)} == {good.key}
    assert {pool.pick(set(), tls=False).result.key for _ in range(200)} == {good.key, mitm.key}
    assert pool.pick({good.key}, tls=True) is None       # no other HTTPS-capable ones left


def test_tls_falls_back_to_all_without_https_results():
    pool = ProxyPool([result("http", 1)])  # e.g. after --fast: HTTPS unknown
    assert pool.pick(set(), tls=True) is not None


@pytest.mark.parametrize("kind, handler", [("socks4", socks4_forward_proxy)])
def test_socks4_upstream_plain_and_tunnel(kind, handler):
    answer, _, _ = run_server([(kind, handler)], plain_get)
    assert answer.startswith(b"HTTP/1.1 200") and answer.endswith(b"ok")
    answer, _, _ = run_server([(kind, handler)], connect_then_get)
    assert b"HTTP/1.1 200 OK" in answer and answer.endswith(b"ok")


def test_plain_http_uses_no_connect_on_http_upstreams():
    """Proxies that can't CONNECT are still fine for plain HTTP."""
    answer, pool, _ = run_server([("http", forward_only_proxy)], plain_get)
    assert answer.startswith(b"HTTP/1.1 200") and answer.endswith(b"ok")
    assert pool.entries[0].ok == 1


def test_connect_without_any_working_proxy_gives_502_not_200():
    answer, _, stats = run_server([("http", None), ("socks5", None)], connect_then_get_raw)
    assert answer.startswith(b"HTTP/1.1 502") and b"Connection established" not in answer
    assert stats.failed == 1


async def connect_then_get_raw(server_port, target_port):
    reader, writer = await asyncio.open_connection("127.0.0.1", server_port)
    writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\n\r\n".encode())
    await writer.drain()
    answer = await asyncio.wait_for(reader.read(65536), 5)
    writer.close()
    return answer


def post_echo(body: bytes):
    async def send(server_port, target_port):
        head = (f"POST http://127.0.0.1:{target_port}/echo HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n"
                f"Content-Length: {len(body)}\r\n\r\n").encode()
        reader, writer = await asyncio.open_connection("127.0.0.1", server_port)
        try:
            writer.write(head + body)
            await writer.drain()
        except ConnectionError:
            pass  # the server aborted before everything was sent – the response still counts
        answer = b""
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(65536), 5)
            except ConnectionError:
                break
            if not chunk:
                break
            answer += chunk
        writer.close()
        return answer
    return send


@pytest.mark.parametrize("kind, handler", [("http", http_forward_proxy), ("socks5", socks5_forward_proxy)])
def test_post_body_reaches_the_target(kind, handler):
    answer, _, _ = run_server([(kind, handler)], post_echo(b"name=wert&x=1"))
    assert answer.startswith(b"HTTP/1.1 200") and answer.endswith(b"name=wert&x=1")


def test_post_body_is_replayed_after_a_silent_proxy():
    answer, pool, stats = run_server([("http", silent_proxy), ("http", http_forward_proxy)], post_echo(b"daten"))
    assert answer.endswith(b"daten")
    assert (pool.entries[0].fail, pool.entries[1].ok) == (1, 1) and stats.recent[-1].attempts == 2


def test_large_body_is_streamed_without_replay():
    body = b"x" * (2 * 1024 * 1024)  # above MAX_REPLAY_BODY
    answer, _, _ = run_server([("http", http_forward_proxy)], post_echo(body))
    assert answer.startswith(b"HTTP/1.1 200") and answer.endswith(body[-100:])
    assert len(answer) > len(body)


def test_connect_on_other_ports_prefers_https_verified_proxies():
    seen = []

    class RecordingPool(OrderedPool):
        def pick(self, exclude, tls=False, **_):
            seen.append(tls)
            return super().pick(exclude, tls)

    run_server([("http", http_forward_proxy)], connect_then_get, pool_cls=RecordingPool)
    assert seen and seen[0] is True   # the target port is arbitrary here, not 443


@pytest.mark.parametrize("raw", [b"CONNECT example.org:70000 HTTP/1.1\r\n\r\n",
                                 b"GET http://example.org:0/ HTTP/1.1\r\n\r\n"])
def test_invalid_ports_give_400(raw):
    async def send(server_port, target_port):
        return await request_via(server_port, raw)

    answer, _, _ = run_server([("socks5", socks5_forward_proxy)], send)
    assert answer.startswith(b"HTTP/1.1 400")


def test_status_2000_is_not_an_established_tunnel():
    answer, pool, _ = run_server([("http", weird_status_proxy)], connect_then_get_raw)
    assert answer.startswith(b"HTTP/1.1 502")
    assert pool.entries[0].fail == 1


def test_streamed_body_through_silent_proxy_counts_as_failure():
    body = b"y" * (2 * 1024 * 1024)
    _answer, pool, stats = run_server([("http", silent_proxy)], post_echo(body))
    assert (stats.ok, stats.failed, pool.entries[0].fail) == (0, 1, 1)
    assert not stats.recent[-1].ok


def test_expect_100_continue_does_not_deadlock():
    async def send(server_port, target_port):
        reader, writer = await asyncio.open_connection("127.0.0.1", server_port)
        writer.write((f"POST http://127.0.0.1:{target_port}/echo HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n"
                      f"Content-Length: 5\r\nExpect: 100-continue\r\n\r\n").encode())
        await writer.drain()
        interim = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)  # waits for 100 Continue
        writer.write(b"hallo")
        await writer.drain()
        rest = await asyncio.wait_for(reader.read(65536), 3)
        writer.close()
        return interim + rest

    answer, _, _ = run_server([("http", http_forward_proxy)], send)
    assert answer.startswith(b"HTTP/1.1 100 Continue") and answer.endswith(b"hallo")


def test_split_tls_client_hello_is_collected_completely():
    async def go():
        tls_srv, tls_port = await serve(tls_record_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        rotating = RotatingServer(OrderedPool([result("http", proxy_port)]), port=0, timeout=3)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(f"CONNECT 127.0.0.1:{tls_port} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            await reader.readuntil(b"\r\n\r\n")
            record = b"\x16\x03\x01\x00\x0a" + b"0123456789"
            writer.write(record[:4])          # record spread over two TCP packets
            await writer.drain()
            await asyncio.sleep(0.2)
            writer.write(record[4:])
            await writer.drain()
            answer = await asyncio.wait_for(reader.read(100), 3)
            writer.close()
            return answer
        finally:
            await rotating.close()
            tls_srv.close()
            proxy_srv.close()

    assert asyncio.run(go()) == b"\x16\x03\x03\x00\x02ok"
