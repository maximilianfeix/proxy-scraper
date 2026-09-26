"""The logic behind the MCP server (#129) – no MCP SDK needed, so this runs on every Python version."""

import asyncio
import json

import pytest

from proxyscraper import agent
from proxyscraper.checker import CheckResult

from .fakes import http_forward_proxy, serve, target_server


def row(n, ptype="http", country="DE", latency=100, **extra):
    base = {"url": f"{ptype}://1.1.1.{n}:80", "proxy": f"1.1.1.{n}:80", "ptype": ptype, "country": country,
            "latency": latency, "exit_ip": f"9.9.9.{n}", "https": True, "anonymity": "elite",
            "org": "Example GmbH", "asn": 64500, "hosting": False, "blocklisted": False, "streak": 1}
    base.update(extra)
    return base


ROWS = [row(1, latency=300), row(2, "socks5", latency=100), row(3, country="US", https=False),
        row(4, "socks4", anonymity="anonymous", hosting=True), row(5, blocklisted=True, streak=30)]
STATS = {"updated": "2026-09-26T12:17:00+00:00", "total": 5, "run_hours": 1}


# --------------------------------------------------------------------------- live list

def fake_fetch(calls, payloads=None, fail=False):
    payloads = payloads or {"proxies.json": ROWS, "stats.json": STATS}

    async def fetch(url, timeout=0, headers=None):
        calls.append(url)
        if fail:
            raise ConnectionError("HTTP 503")
        return json.dumps(payloads[url.rsplit("/", 1)[1]]).encode()
    return fetch


def test_live_list_is_cached_for_a_few_minutes():
    calls, now = [], [1000.0]
    source = agent.LiveSource(fetch=fake_fetch(calls), clock=lambda: now[0], ttl=300)

    async def go():
        first = await source.get()
        now[0] += 200
        await source.get()
        now[0] += 200  # 400 s after the first load
        return first, await source.get()

    first, _ = asyncio.run(go())
    assert len(first.rows) == 5 and first.updated == STATS["updated"] and first.run_hours == 1
    assert len(calls) == 4  # proxies.json + stats.json, twice – the middle call came from the cache


def test_a_failed_refresh_keeps_the_old_list():
    calls, now = [], [0.0]
    good = fake_fetch(calls)
    source = agent.LiveSource(fetch=good, clock=lambda: now[0], ttl=300)

    async def go():
        await source.get()
        source.fetch = fake_fetch(calls, fail=True)
        now[0] += 1000
        return await source.get()

    assert len(asyncio.run(go()).rows) == 5


def test_no_list_at_all_says_what_to_do():
    source = agent.LiveSource(fetch=fake_fetch([], fail=True))
    with pytest.raises(agent.AgentError, match="check_proxies"):
        asyncio.run(source.get())


# --------------------------------------------------------------------------- filters

def urls(rows):
    return [r["url"] for r in rows]


def test_select_filters_and_sorts_fastest_first():
    assert urls(agent.select(ROWS))[:2] == ["socks5://1.1.1.2:80", "http://1.1.1.3:80"]
    assert urls(agent.select(ROWS, protocol="socks5")) == ["socks5://1.1.1.2:80"]
    assert set(urls(agent.select(ROWS, countries=["us"]))) == {"http://1.1.1.3:80"}  # case doesn't matter
    assert "http://1.1.1.3:80" not in urls(agent.select(ROWS, https_only=True))
    assert "socks4://1.1.1.4:80" not in urls(agent.select(ROWS, elite_only=True))
    assert "socks4://1.1.1.4:80" not in urls(agent.select(ROWS, exclude_datacenter=True))
    assert "http://1.1.1.5:80" not in urls(agent.select(ROWS, exclude_blocklisted=True))
    assert urls(agent.select(ROWS, max_latency_ms=150)) == ["socks5://1.1.1.2:80", "http://1.1.1.3:80",
                                                            "socks4://1.1.1.4:80", "http://1.1.1.5:80"]


def test_stable_means_listed_for_24_hours_whatever_the_interval():
    assert urls(agent.select(ROWS, stable_only=True, run_hours=1)) == ["http://1.1.1.5:80"]  # streak 30 >= 24
    assert len(agent.select(ROWS, stable_only=True, run_hours=6)) == 1                      # 30 runs * 6 h


def test_bad_filters_are_explained():
    with pytest.raises(agent.AgentError, match="protocol"):
        agent.select(ROWS, protocol="ftp")
    with pytest.raises(agent.AgentError, match="two-letter"):
        agent.select(ROWS, countries=["Germany"])


def test_proxy_as_an_agent_sees_it():
    shown = agent.describe(row(7, "socks5", streak=5, org="Hetzner Online GmbH", hosting=True), run_hours=1)
    assert shown == {"url": "socks5://1.1.1.7:80", "protocol": "socks5", "address": "1.1.1.7:80", "country": "DE",
                     "latency_ms": 100, "https": True, "anonymity": "elite", "provider": "Hetzner Online GmbH",
                     "datacenter": True, "blocklisted": False, "up_for_hours": 5}


def test_describe_takes_check_results_too():
    result = CheckResult("http 2.2.2.2:8080", "http", "2.2.2.2:8080", 250, "9.9.9.9", https=False, country="NL")
    shown = agent.describe(result)
    assert shown["url"] == "http://2.2.2.2:8080" and shown["latency_ms"] == 250 and shown["up_for_hours"] is None


def test_the_note_helps_when_little_matches():
    note = agent.shortage_note(ROWS, wanted=10, matched=1, countries=["US"])
    assert "1 proxy" in note and "DE (4)" in note  # suggests where there are more


# --------------------------------------------------------------------------- fetching pages

def test_only_public_http_targets_are_fetched():
    for bad in ("file:///etc/passwd", "ftp://example.com/", "http://localhost/", "http://127.0.0.1:8080/",
                "http://10.0.0.5/", "http://[::1]/", "https://169.254.169.254/latest/meta-data/", "example.com"):
        with pytest.raises(agent.AgentError):
            agent.check_target(bad)
    assert agent.check_target("https://example.com/a?b=1") == "https://example.com/a?b=1"


def test_html_becomes_readable_text():
    html = b"""<html><head><title>T</title><style>p{color:red}</style><script>alert(1)</script></head>
    <body><h1>Hello &amp; welcome</h1><p>First   line</p><ul><li>one</li><li>two</li></ul>
    <noscript>enable js</noscript><p>Last</p></body></html>"""
    text = agent.html_to_text(html.decode())
    assert text.splitlines() == ["T", "Hello & welcome", "First line", "one", "two", "Last"]


def with_fetcher(client, rows_for=None, strategy="weighted"):
    """A real RotatingServer in front of real local proxies and a local target site."""
    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        rows = (rows_for or (lambda port: [row(1, proxy=f"127.0.0.1:{port}", url=f"http://127.0.0.1:{port}")]))(
            proxy_port)
        live = agent.LiveList(rows=rows, stats=STATS, loaded_at=0.0)

        class Source:
            async def get(self):
                return live

        fetcher = agent.PageFetcher(Source(), allow_private=True, timeout=5, strategy=strategy)
        try:
            return await client(fetcher, target_port)
        finally:
            await fetcher.close()
            target_srv.close()
            proxy_srv.close()
    return asyncio.run(go())


def test_fetch_goes_through_a_proxy_and_says_which():
    async def client(fetcher, port):
        return await fetcher.fetch(f"http://127.0.0.1:{port}/ok")

    page = with_fetcher(client)
    assert page["status"] == 200 and page["text"] == "ok" and not page["truncated"]
    assert page["via"].startswith("http://127.0.0.1:")


def test_fetch_switches_to_the_next_proxy_when_one_is_dead():
    def rows(port):
        return [row(1, proxy="127.0.0.1:1", url="http://127.0.0.1:1", latency=10),  # nothing listens there
                row(2, proxy=f"127.0.0.1:{port}", url=f"http://127.0.0.1:{port}", latency=500)]

    async def client(fetcher, port):
        page = await fetcher.fetch(f"http://127.0.0.1:{port}/ok")
        return page, fetcher.server.stats.recent[-1].attempts

    page, attempts = with_fetcher(client, rows, strategy="fastest")  # the dead one is the fastest: tried first
    assert page["status"] == 200 and attempts == 2
    assert page["via"] != "http://127.0.0.1:1"


def test_fetch_reports_http_errors_instead_of_failing():
    async def client(fetcher, port):
        return await fetcher.fetch(f"http://127.0.0.1:{port}/forbidden")

    page = with_fetcher(client)
    assert page["status"] == 403


def test_fetch_cuts_long_pages():
    async def client(fetcher, port):
        return await fetcher.fetch(f"http://127.0.0.1:{port}/ok", max_chars=1)

    page = with_fetcher(client)
    assert page["text"] == "o" and page["truncated"] is True


def test_no_matching_proxy_is_explained():
    async def client(fetcher, port):
        return await fetcher.fetch(f"http://127.0.0.1:{port}/ok", country="JP")

    with pytest.raises(agent.AgentError, match="JP"):
        with_fetcher(client)


# --------------------------------------------------------------------------- fresh checks

def test_fresh_check_uses_the_live_list_and_reports_progress(monkeypatch):
    seen, ticks = {}, []

    async def fake_find(**kwargs):
        seen.update(kwargs)
        await asyncio.sleep(0.05)
        return [CheckResult("socks5 3.3.3.3:1080", "socks5", "3.3.3.3:1080", 90, "9.9.9.9", https=True,
                            country="DE", anonymity="elite")]

    monkeypatch.setattr(agent, "find_proxies_async", fake_find)

    async def progress(elapsed, message):
        ticks.append(message)

    found = asyncio.run(agent.check_fresh(want=5, protocol="socks5", countries=["de"], https_only=True,
                                          progress=progress, tick=0.01))
    assert [p["url"] for p in found] == ["socks5://3.3.3.3:1080"]
    assert seen["_recheck"] == "live" and seen["types"] == ["socks5"] and seen["countries"] == ["DE"]
    assert seen["want"] == 5 and seen["https"] is True and seen["verbose"] is False
    assert ticks  # the client heard from us while the check ran


def test_full_scan_mode_starts_from_all_sources(monkeypatch):
    seen = {}

    async def fake_find(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(agent, "find_proxies_async", fake_find)
    asyncio.run(agent.check_fresh(want=3, mode="full"))
    assert seen["_recheck"] is None and seen["types"] == ["http", "socks4", "socks5"]


def test_closing_the_server_ends_open_tunnels():
    """A tunnel whose target never hangs up must not keep close() waiting or leave tasks behind."""
    from proxyscraper.server import ProxyPool, RotatingServer

    async def silent_target(reader, writer):
        await reader.read()  # holds the connection until the other side goes away

    async def go():
        target_srv, target_port = await serve(silent_target)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        result = CheckResult(f"http 127.0.0.1:{proxy_port}", "http", f"127.0.0.1:{proxy_port}", 100, "9.9.9.9",
                             https=True)
        rotating = RotatingServer(ProxyPool([result]), port=0, timeout=3)
        await rotating.start()
        _reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
        writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        writer.write(b"\x16\x03\x01")  # a first packet, so the tunnel is really in use
        await writer.drain()
        await asyncio.sleep(0.3)
        await asyncio.wait_for(rotating.close(), 3)
        left = [t for t in asyncio.all_tasks() if "_handle" in repr(t) and not t.done()]
        writer.close()
        target_srv.close()
        proxy_srv.close()
        return left

    assert asyncio.run(go()) == []


def dead_rows(port, n=3):
    """n dead proxies that are faster than the one working proxy on `port`."""
    dead = [row(10 + i, proxy=f"127.0.0.1:{i + 1}", url=f"http://127.0.0.1:{i + 1}", latency=10 + i) for i in range(n)]
    return [*dead, row(2, proxy=f"127.0.0.1:{port}", url=f"http://127.0.0.1:{port}", latency=900)]


def test_agents_get_more_attempts_than_the_command_line_server():
    async def client(fetcher, port):
        page = await fetcher.fetch(f"http://127.0.0.1:{port}/ok")
        return page, fetcher.server.stats.recent[-1].attempts

    page, attempts = with_fetcher(client, dead_rows, strategy="fastest")  # 3 dead ones first, then the working one
    assert page["status"] == 200 and attempts == 4


def test_no_proxy_getting_through_is_an_error_not_a_502_page():
    async def client(fetcher, port):
        return await fetcher.fetch(f"http://127.0.0.1:{port}/ok")

    def only_dead(port):
        return dead_rows(port)[:3]

    with pytest.raises(agent.AgentError, match="block"):
        with_fetcher(client, only_dead)


async def cut_off_target(reader, writer):
    """Promises 1000 bytes, sends 10 and hangs up – like a proxy that drops the connection mid-download."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n0123456789")
    await writer.drain()
    writer.close()


def test_a_download_that_breaks_off_is_explained_not_a_crash():
    async def go():
        target_srv, target_port = await serve(cut_off_target)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        live = agent.LiveList(rows=[row(1, proxy=f"127.0.0.1:{proxy_port}", url=f"http://127.0.0.1:{proxy_port}")],
                              stats=STATS, loaded_at=0.0)

        class Source:
            async def get(self):
                return live

        fetcher = agent.PageFetcher(Source(), allow_private=True, timeout=5)
        try:
            await fetcher.fetch(f"http://127.0.0.1:{target_port}/big")
        finally:
            await fetcher.close()
            target_srv.close()
            proxy_srv.close()

    with pytest.raises(agent.AgentError, match="broke off"):
        asyncio.run(go())


# --------------------------------------------------------------------------- review of #130

def test_fetch_never_bypasses_the_proxy(monkeypatch):
    """no_proxy and macOS' proxy exceptions (*.local, 169.254/16) must not send a request out directly."""
    import urllib.request
    monkeypatch.setenv("no_proxy", "*")
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: True)

    async def client(fetcher, port):
        page = await fetcher.fetch(f"http://127.0.0.1:{port}/ok")
        return page, fetcher.server.stats.requests

    page, requests = with_fetcher(client)
    assert page["status"] == 200 and page["via"] and requests == 1


def test_redirects_are_followed_and_checked_like_the_first_url():
    async def followed(fetcher, port):
        return await fetcher.fetch(f"http://127.0.0.1:{port}/redirect")

    page = with_fetcher(followed)
    assert page["status"] == 200 and page["text"] == "ok" and page["final_url"].endswith("/ok")

    def refuse_ok(url):
        if url.endswith("/ok"):
            raise agent.AgentError("private")
        return url

    async def refused(fetcher, port):
        fetcher.check = refuse_ok  # like a public page redirecting to 10.0.0.1
        return await fetcher.fetch(f"http://127.0.0.1:{port}/redirect")

    with pytest.raises(agent.AgentError, match="private"):
        with_fetcher(refused)


def test_disguised_local_addresses_are_refused_too():
    for bad in ("http://localhost./", "http://127.1/", "http://2130706433/", "http://0x7f000001/",
                "http://printer.local/", "http://[::ffff:127.0.0.1]/"):
        with pytest.raises(agent.AgentError):
            agent.check_target(bad)


def test_parallel_fetches_on_a_fresh_fetcher():
    async def client(fetcher, port):
        return await asyncio.gather(*(fetcher.fetch(f"http://127.0.0.1:{port}/ok") for _ in range(3)))

    assert [p["status"] for p in with_fetcher(client)] == [200, 200, 200]


async def slow_target(reader, writer):
    await reader.readuntil(b"\r\n\r\n")
    await asyncio.sleep(0.3)
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nslow")
    await writer.drain()
    writer.close()


def test_a_slow_fetch_reports_progress():
    ticks = []

    async def go():
        target_srv, target_port = await serve(slow_target)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        live = agent.LiveList(rows=[row(1, proxy=f"127.0.0.1:{proxy_port}", url=f"http://127.0.0.1:{proxy_port}")],
                              stats=STATS, loaded_at=0.0)

        class Source:
            async def get(self):
                return live

        async def progress(elapsed, message):
            ticks.append(message)

        fetcher = agent.PageFetcher(Source(), allow_private=True, timeout=5)
        try:
            return await fetcher.fetch(f"http://127.0.0.1:{target_port}/", progress=progress, tick=0.05)
        finally:
            await fetcher.close()
            target_srv.close()
            proxy_srv.close()

    assert asyncio.run(go())["text"] == "slow" and ticks


async def cutting_proxy(reader, writer):
    """Answers every request itself with a body that stops early."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n0123")
    await writer.drain()
    writer.close()


def test_a_proxy_that_broke_off_is_not_picked_again():
    async def go():
        target_srv, target_port = await serve(target_server)
        bad_srv, bad_port = await serve(cutting_proxy)
        good_srv, good_port = await serve(http_forward_proxy)
        live = agent.LiveList(rows=[row(1, proxy=f"127.0.0.1:{bad_port}", url=f"http://127.0.0.1:{bad_port}",
                                        latency=10),
                                    row(2, proxy=f"127.0.0.1:{good_port}", url=f"http://127.0.0.1:{good_port}",
                                        latency=900)], stats=STATS, loaded_at=0.0)

        class Source:
            async def get(self):
                return live

        fetcher = agent.PageFetcher(Source(), allow_private=True, timeout=5, strategy="fastest")
        try:
            return await fetcher.fetch(f"http://127.0.0.1:{target_port}/ok"), good_port
        finally:
            await fetcher.close()
            for s in (target_srv, bad_srv, good_srv):
                s.close()

    page, good_port = asyncio.run(go())
    assert page["text"] == "ok" and page["via"] == f"http://127.0.0.1:{good_port}"


def test_while_github_is_down_the_old_list_is_served_without_waiting():
    calls, now = [], [0.0]
    source = agent.LiveSource(fetch=fake_fetch(calls), clock=lambda: now[0], ttl=300)

    async def go():
        await source.get()
        source.fetch = fake_fetch(calls, fail=True)
        now[0] += 1000
        await source.get()                # tries once, fails, serves the old list
        tried = len(calls)
        now[0] += 10
        await source.get()                # shortly after: straight from the cache
        return tried, len(calls)

    tried, after = asyncio.run(go())
    assert after == tried


def test_an_unknown_charset_falls_back_to_utf8():
    assert agent.decode_body("grüße".encode(), "utf8mb4") == "grüße"
    assert agent.decode_body("grüße".encode("latin-1"), "latin-1") == "grüße"
