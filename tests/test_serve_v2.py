"""Proxy-Server v2: Strategien, Sticky Sessions, Auswahl per Benutzername, SOCKS5-Eingang, Status, Auffrischen."""

import asyncio
import base64
import json
import random
import socket

import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.server import ProxyPool, RotatingServer
from proxyscraper.server.pool import Selection
from proxyscraper.server.status import selection_from_headers

from .fakes import http_forward_proxy, serve, target_server


def result(n, latency=100, country="DE", ptype="http", https=True):
    proxy = f"10.0.0.{n}:80"
    return CheckResult(f"{ptype} {proxy}", ptype, proxy, latency, "9.9.9.9", https=https, country=country)


@pytest.mark.parametrize("username, expected", [
    ("country-de", Selection(country="DE")),
    ("country-us-type-socks5", Selection(country="US", ptype="socks5")),
    ("session-abc123", Selection(session="abc123")),
    ("user_country_de_session_x", Selection(country="DE", session="x")),
    ("type-ftp", Selection()),        # unbekannter Typ wird ignoriert
    ("", Selection()),
])
def test_selection_from_username(username, expected):
    assert Selection.from_username(username) == expected


def test_selection_from_proxy_authorization_header():
    token = base64.b64encode(b"country-nl-session-7:egal")
    assert selection_from_headers([(b"Proxy-Authorization", b"Basic " + token)]) == Selection("NL", "", "7")
    assert selection_from_headers([(b"Proxy-Authorization", b"Basic !!kaputt")]) == Selection()
    assert selection_from_headers([]) == Selection()


def test_round_robin_cycles_through_everyone():
    pool = ProxyPool([result(i) for i in range(1, 4)], strategy="round-robin")
    picks = [pool.pick(set()).result.proxy for _ in range(6)]
    assert picks[:3] == picks[3:] and len(set(picks)) == 3


def test_fastest_takes_the_fastest_and_spreads_load():
    pool = ProxyPool([result(1, latency=900), result(2, latency=100), result(3, latency=400)], strategy="fastest")
    first = pool.pick(set())
    assert first.result.proxy == "10.0.0.2:80"
    first.active = 1  # beschäftigt -> der schnellste freie ist dran, auch wenn er viel langsamer ist
    assert pool.pick(set()).result.proxy == "10.0.0.3:80"
    for e in pool.entries:
        e.active = 2
    pool.entries[0].active = 1  # alle beschäftigt -> der am wenigsten beschäftigte
    assert pool.pick(set()) is pool.entries[0]


def test_random_strategy_uses_everyone():
    pool = ProxyPool([result(i) for i in range(1, 5)], strategy="random", rng=random.Random(1))
    assert {pool.pick(set()).result.proxy for _ in range(60)} == {f"10.0.0.{i}:80" for i in range(1, 5)}


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError):
        ProxyPool([], strategy="magic")


def test_country_and_type_are_strict():
    pool = ProxyPool([result(1, country="DE"), result(2, country="US", ptype="socks5")])
    assert pool.pick(set(), selection=Selection(country="US")).result.proxy == "10.0.0.2:80"
    assert pool.pick(set(), selection=Selection(ptype="socks5")).result.country == "US"
    assert pool.pick(set(), selection=Selection(country="FR")) is None  # lieber Fehler als falsches Land


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_sticky_target_keeps_the_proxy_until_it_expires():
    clock = Clock()
    pool = ProxyPool([result(i) for i in range(1, 6)], strategy="round-robin", sticky_seconds=60, clock=clock)
    first = pool.pick(set(), target="shop.example:443")
    assert all(pool.pick(set(), target="shop.example:443") is first for _ in range(5))
    assert pool.pick(set(), target="other.example:443") is not first  # andere Seite, andere Wahl
    clock.now += 61
    assert pool.pick(set(), target="shop.example:443") is not first


def test_session_sticks_even_without_sticky_option():
    pool = ProxyPool([result(i) for i in range(1, 6)], strategy="round-robin")
    first = pool.pick(set(), selection=Selection(session="a"))
    assert all(pool.pick(set(), selection=Selection(session="a")) is first for _ in range(4))
    assert pool.pick(set(), selection=Selection(session="b")) is not first


def test_session_moves_on_when_its_proxy_dies():
    pool = ProxyPool([result(i) for i in range(1, 4)], strategy="round-robin")
    first = pool.pick(set(), selection=Selection(session="a"))
    for _ in range(3):
        pool.report(first, False)
    assert first.disabled
    assert pool.pick(set(), selection=Selection(session="a")) is not first


def test_refresh_brings_back_proxies_that_work_again():
    pool = ProxyPool([result(1), result(2)])
    for entry in pool.entries:
        for _ in range(3):
            pool.report(entry, False)
    server = RotatingServer(pool)

    async def recheck(r):
        return r.proxy == "10.0.0.1:80"

    assert asyncio.run(server.refresh_once(recheck)) == 1
    assert [e.disabled for e in pool.entries] == [False, True] and server.revived == 1


# ----------------------------------------------------------------------------- echte Verbindungen


def run_with_server(pool_results, client):
    """Zielserver + ein Upstream pro Ergebnis (alle HTTP-Proxys auf localhost) + rotierender Server."""
    async def go():
        target_srv, target_port = await serve(target_server)
        servers, results, seen = [target_srv], [], []
        for r in pool_results:
            async def handler(reader, writer, country=r.country):
                seen.append(country)
                await http_forward_proxy(reader, writer)
            srv, port = await serve(handler)
            servers.append(srv)
            results.append(CheckResult(f"http 127.0.0.1:{port}", "http", f"127.0.0.1:{port}", r.latency,
                                       "9.9.9.9", https=True, country=r.country))
        rotating = RotatingServer(ProxyPool(results), port=0, timeout=3)
        await rotating.start()
        try:
            return await client(rotating.port, target_port), seen, rotating
        finally:
            await rotating.close()
            for s in servers:
                s.close()
    return asyncio.run(go())


async def socks5_get(server_port, target_port, username=b""):
    reader, writer = await asyncio.open_connection("127.0.0.1", server_port)
    if username:
        writer.write(b"\x05\x01\x02")
        await writer.drain()
        assert await reader.readexactly(2) == b"\x05\x02"
        writer.write(b"\x01" + bytes([len(username)]) + username + b"\x01x")
        await writer.drain()
        assert await reader.readexactly(2) == b"\x01\x00"
    else:
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        assert await reader.readexactly(2) == b"\x05\x00"
    writer.write(b"\x05\x01\x00\x01" + socket.inet_aton("127.0.0.1") + target_port.to_bytes(2, "big"))
    await writer.drain()
    reply = await asyncio.wait_for(reader.readexactly(10), 5)
    if reply[1] != 0:
        writer.close()
        return reply, b""
    writer.write(f"GET /ok HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n\r\n".encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(65536), 5)
    writer.close()
    return reply, data


def test_socks5_clients_are_served_on_the_same_port():
    (reply, data), _, _ = run_with_server([result(1)], socks5_get)
    assert reply[1] == 0 and b"200 OK" in data


def test_socks5_username_picks_the_country():
    async def client(sp, tp):
        return await socks5_get(sp, tp, username=b"country-us")

    (reply, data), seen, _ = run_with_server([result(1, country="DE"), result(2, country="US")], client)
    assert reply[1] == 0 and b"200 OK" in data and seen == ["US"]


def test_socks5_unknown_country_is_refused_cleanly():
    async def client(sp, tp):
        return await socks5_get(sp, tp, username=b"country-fr")

    (reply, _data), seen, _ = run_with_server([result(1, country="DE")], client)
    assert reply[1] == 0x04 and seen == []


def test_http_client_picks_the_country_with_proxy_authorization():
    async def client(sp, tp):
        reader, writer = await asyncio.open_connection("127.0.0.1", sp)
        token = base64.b64encode(b"country-us:x").decode()
        writer.write(f"GET http://127.0.0.1:{tp}/ok HTTP/1.1\r\nHost: 127.0.0.1:{tp}\r\n"
                     f"Proxy-Authorization: Basic {token}\r\n\r\n".encode())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(65536), 5)
        writer.close()
        return data

    data, seen, _ = run_with_server([result(1, country="DE"), result(2, country="US")], client)
    assert b"200 OK" in data and seen == ["US"]


def test_status_endpoint_reports_the_pool():
    async def client(sp, tp):
        reader, writer = await asyncio.open_connection("127.0.0.1", sp)
        writer.write(b"GET /__proxy-scraper/status HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(1 << 20), 5)
        writer.close()
        return data

    data, _, _ = run_with_server([result(1), result(2, country="US")], client)
    head, _, body = data.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.1 200") and b"application/json" in head
    status = json.loads(body)
    assert status["pool"]["total"] == 2 and status["strategy"] == "weighted"
    assert {p["country"] for p in status["proxies"]} == {"DE", "US"}



def test_busy_counter_goes_back_to_zero():
    async def client(sp, tp):
        for _ in range(3):
            await socks5_get(sp, tp)

    _, _, rotating = run_with_server([result(1), result(2)], client)
    assert all(e.active == 0 for e in rotating.pool.entries)


def test_busy_counter_is_released_when_a_proxy_fails():
    pool = ProxyPool([result(1)])
    server = RotatingServer(pool, timeout=1)

    async def go():
        # 10.0.0.1:80 ist nicht erreichbar -> UpstreamError, Reservierung muss wieder frei sein
        return await server._open_next(set(), "example.com", 80, tls=False, tunnel=True)

    assert asyncio.run(go()) is None and pool.entries[0].active == 0


def test_pool_recheck_ignores_the_unreachable_cache():
    from proxyscraper.app import pool_recheck

    class Checker:
        def __init__(self):
            self.unreachable = {"10.0.0.1:80"}

        async def check(self, key):
            return None if key.split(" ")[1] in self.unreachable else object()

    checker = Checker()
    assert asyncio.run(pool_recheck(checker)(result(1))) is True


@pytest.mark.parametrize("greeting", [b"\x05\x02\x00", b"\x05\x01\x00\x05\x01\x00\x03\x05ab", b"\x05"])
def test_broken_socks5_clients_are_closed_quietly(greeting):
    errors = []

    async def go():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _loop, ctx: errors.append(ctx))
        rotating = RotatingServer(ProxyPool([result(1)]), port=0, timeout=0.5)
        await rotating.start()
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(greeting)
            await writer.drain()
            writer.close()  # mitten im Handshake auflegen
            await asyncio.sleep(0.8)
        finally:
            await rotating.close()

    asyncio.run(go())
    assert errors == []



def test_only_the_exact_status_path_answers():
    async def client(sp, tp):
        out = []
        for path in (b"/__proxy-scraper/status?x=1", b"/__proxy-scraper/status-extra"):
            reader, writer = await asyncio.open_connection("127.0.0.1", sp)
            writer.write(b"GET " + path + b" HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            await writer.drain()
            out.append(await asyncio.wait_for(reader.read(1 << 20), 5))
            writer.close()
        return out

    (ok, typo), _, _ = run_with_server([result(1)], client)
    assert ok.startswith(b"HTTP/1.1 200") and typo.startswith(b"HTTP/1.1 404")



@pytest.mark.parametrize("host, loopback", [("127.0.0.1", True), ("::1", True), ("localhost", True),
                                            ("0.0.0.0", False), ("192.168.1.5", False)])
def test_is_loopback(host, loopback):
    from proxyscraper.app import is_loopback
    assert is_loopback(host) is loopback


def test_serve_host_option_roundtrip():
    from proxyscraper.cli import parse_args
    from proxyscraper.options import RunOptions
    opts = RunOptions.from_args(parse_args(["--serve", "--serve-host", "0.0.0.0"]))
    assert opts.serve_host == "0.0.0.0" and "--serve-host" in opts.to_argv()
    assert RunOptions.from_args(parse_args(opts.to_argv())) == opts
    assert "--serve-host" not in RunOptions.from_args(parse_args(["--serve"])).to_argv()
