"""Invalid target names aren't the proxy's fault, and requests to a non-default port send it in the Host header."""

import asyncio

import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.netio import host_header, http_request
from proxyscraper.server import ProxyPool, RotatingServer
from proxyscraper.server.upstream import Unsupported, _connect_through

from .fakes import serve, socks5_forward_proxy


def test_host_header_has_the_port_unless_it_is_the_default():
    assert host_header("example.com", None, False) == "example.com"
    assert host_header("example.com", 80, False) == "example.com"
    assert host_header("example.com", 443, True) == "example.com"
    assert host_header("example.com", 8080, False) == "example.com:8080"
    assert host_header("example.com", 80, True) == "example.com:80"
    assert host_header("2606:4700::1", 8443, True) == "[2606:4700::1]:8443"


def test_http_request_sends_the_port_in_the_host_header():
    async def go():
        seen = []

        async def handler(reader, writer):
            seen.append((await reader.readuntil(b"\r\n\r\n")).split(b"\r\n")[1])
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
            writer.close()

        server, port = await serve(handler)
        try:
            await http_request(f"http://127.0.0.1:{port}/list.txt")
        finally:
            server.close()
        return seen, port

    seen, port = asyncio.run(go())
    assert seen == [f"Host: 127.0.0.1:{port}".encode()]


BAD_HOSTS = ["a" * 70 + ".com", "example..com", "a" * 300, "evil.com\r\nX-Injected: 1", "a b.com", ""]


@pytest.mark.parametrize("host", BAD_HOSTS)
def test_unusable_host_names_are_unsupported_not_a_proxy_failure(host):
    class Sink:
        def write(self, data):
            raise AssertionError("nothing may be sent to the proxy")

    for ptype in ("http", "socks4", "socks5"):
        with pytest.raises(Unsupported):
            asyncio.run(_connect_through(ptype, "1.2.3.4:1080", None, Sink(), host, 443))


def test_a_bad_host_does_not_disable_proxies():
    async def go():
        proxies = [await serve(socks5_forward_proxy) for _ in range(3)]
        results = [CheckResult(f"socks5 127.0.0.1:{p}", "socks5", f"127.0.0.1:{p}", 100, "9.9.9.9", https=True)
                   for _, p in proxies]
        rotating = RotatingServer(ProxyPool(results), port=0, timeout=2)
        await rotating.start()
        try:
            for _ in range(4):
                reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
                writer.write(b"CONNECT example..com:443 HTTP/1.1\r\nHost: example..com:443\r\n\r\n")
                await writer.drain()
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
                assert head.startswith(b"HTTP/1.1 502")
                writer.close()
            return rotating.pool
        finally:
            await rotating.close()
            for srv, _ in proxies:
                srv.close()

    pool = asyncio.run(go())
    assert len(pool.usable) == 3
    assert all(e.fail == 0 for e in pool.entries)
