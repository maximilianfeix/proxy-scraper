"""ProxyRotator: get a URL through the live list, switching proxies until one delivers."""

import asyncio

import pytest

from proxyscraper import ProxyRotator, agent
from tests.fakes import http_forward_proxy, serve, target_server
from tests.test_agent import STATS, row


def source_for(rows):
    live = agent.LiveList(rows=rows, stats=STATS, loaded_at=0.0)

    class Source:
        async def get(self):
            return live
    return Source()


async def local_setup():
    target_srv, target_port = await serve(target_server)
    proxy_srv, proxy_port = await serve(http_forward_proxy)
    rows = [row(1, proxy="127.0.0.1:1", url="http://127.0.0.1:1", latency=10),  # nothing listens there
            row(2, proxy=f"127.0.0.1:{proxy_port}", url=f"http://127.0.0.1:{proxy_port}", latency=500)]
    return target_srv, proxy_srv, target_port, rows


def test_async_get_switches_past_a_dead_proxy():
    async def go():
        target_srv, proxy_srv, port, rows = await local_setup()
        try:
            async with ProxyRotator(_source=source_for(rows), _allow_private=True, timeout=5) as rotator:
                return await rotator.aget(f"http://127.0.0.1:{port}/ok")
        finally:
            target_srv.close()
            proxy_srv.close()
    response = asyncio.run(go())
    assert response.status == 200 and response.content == b"ok" and response.text == "ok"
    assert response.via.endswith(":" + response.via.rsplit(":", 1)[1]) and "127.0.0.1:1" not in response.via


def test_sync_get_works_from_plain_code():
    # the sync version keeps its own event loop in a thread: the proxy server lives across calls
    loop = asyncio.new_event_loop()
    target_srv, proxy_srv, port, rows = loop.run_until_complete(local_setup())
    import threading
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        with ProxyRotator(_source=source_for(rows), _allow_private=True, timeout=5) as rotator:
            first = rotator.get(f"http://127.0.0.1:{port}/ok")
            second = rotator.get(f"http://127.0.0.1:{port}/ok")
        assert first.status == second.status == 200
    finally:
        loop.call_soon_threadsafe(target_srv.close)
        loop.call_soon_threadsafe(proxy_srv.close)
        loop.call_soon_threadsafe(loop.stop)


def test_nothing_matching_is_a_clear_error():
    async def go():
        async with ProxyRotator(country="JP", _source=source_for([row(1)]), _allow_private=True) as rotator:
            await rotator.aget("http://127.0.0.1:9/")
    with pytest.raises(ConnectionError, match="JP"):
        asyncio.run(go())


def test_private_addresses_are_refused_by_default():
    async def go():
        async with ProxyRotator(_source=source_for([row(1)])) as rotator:
            await rotator.aget("http://127.0.0.1/")
    with pytest.raises(ValueError):
        asyncio.run(go())


def response(headers, content=b"x", truncated=False):
    from proxyscraper.api import ProxyResponse, _Headers
    return ProxyResponse(200, "u", "u", _Headers(headers), content, "http://p:1", None, 1, truncated=truncated)


def test_headers_ignore_case_and_keep_every_value():
    r = response([("content-type", "text/html"), ("Set-Cookie", "a=1"), ("set-cookie", "b=2")])
    assert r.headers["Content-Type"] == "text/html" and r.headers.get("CONTENT-TYPE") == "text/html"
    assert r.headers.get_all("Set-Cookie") == ["a=1", "b=2"]


def test_the_charset_is_read_like_a_browser_would():
    latin = "Grüße".encode("latin-1")
    assert response([("Content-Type", 'text/html; charset="ISO-8859-1"')], latin).text == "Grüße"
    assert response([("Content-Type", "text/html; Charset=latin-1")], latin).text == "Grüße"
    assert response([("Content-Type", "text/html; charset=nonsense")], "ä".encode()).text == "ä"


def test_a_cut_off_body_says_so():
    r = response([], b"x" * 10, truncated=True)
    assert r.truncated
    with pytest.raises(ConnectionError, match="cut off"):
        r.raise_for_status()


def test_sync_get_from_many_threads_shares_one_loop(monkeypatch):
    import concurrent.futures as cf

    from proxyscraper import api

    async def fake_aget(self, url):
        return response([], url.encode())
    monkeypatch.setattr(api.ProxyRotator, "_aget", fake_aget)
    rotator = api.ProxyRotator()
    with cf.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(rotator.get, [f"http://x/{i}" for i in range(32)]))
    assert [r.content for r in results] == [f"http://x/{i}".encode() for i in range(32)]
    loops = rotator._loop
    rotator.close()
    assert loops.is_closed()


def test_mixing_sync_and_async_is_refused(monkeypatch):
    from proxyscraper import api

    async def fake_aget(self, url):
        return response([])
    monkeypatch.setattr(api.ProxyRotator, "_aget", fake_aget)
    rotator = api.ProxyRotator()
    rotator.get("http://x/")
    with pytest.raises(RuntimeError, match="async"):
        asyncio.run(rotator.aget("http://x/"))
    rotator.close()


def get_through(proxy_url: str, url: str):
    """A plain GET through an HTTP proxy URL with a login, the way requests or httpx send it."""
    import base64
    import http.client
    from urllib.parse import urlsplit

    p = urlsplit(proxy_url)
    login = base64.b64encode(f"{p.username}:{p.password}".encode()).decode()
    conn = http.client.HTTPConnection(p.hostname, p.port, timeout=10)
    conn.request("GET", url, headers={"Proxy-Authorization": f"Basic {login}"})
    response = conn.getresponse()
    return response.status, response.read()


def test_proxy_url_is_a_rotating_proxy_for_any_library():
    loop = asyncio.new_event_loop()
    target_srv, proxy_srv, port, rows = loop.run_until_complete(local_setup())
    import threading
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        with ProxyRotator(_source=source_for(rows), _allow_private=True, timeout=5) as rotator:
            url = rotator.proxy_url()
            assert url.startswith("http://") and "@127.0.0.1:" in url
            # the dead proxy is tried and skipped inside, the client just gets its page
            assert get_through(url, f"http://127.0.0.1:{port}/ok") == (200, b"ok")
            assert rotator.proxy_url() == url  # the same server for the rotator's lifetime
    finally:
        loop.call_soon_threadsafe(target_srv.close)
        loop.call_soon_threadsafe(proxy_srv.close)
        loop.call_soon_threadsafe(loop.stop)


def test_proxy_url_carries_country_and_protocol_and_refuses_what_isnt_there():
    async def go(**wishes):
        rows = [row(1, country="DE", ptype="socks5")]
        async with ProxyRotator(_source=source_for(rows), _allow_private=True, **wishes) as rotator:
            return await rotator.aproxy_url()
    assert "//country-de-type-socks5:" in asyncio.run(go(country="de", protocol="socks5"))

    async def for_playwright():
        async with ProxyRotator(_source=source_for([row(1)]), _allow_private=True) as rotator:
            return await rotator.aproxy_url(), await rotator.aplaywright_proxy()
    url, settings = asyncio.run(for_playwright())
    # Playwright ignores a login inside "server": it wants the parts on their own
    assert settings["server"] == "http://" + url.rsplit("@", 1)[1] and "@" not in settings["server"]
    assert url == f"http://{settings['username']}:{settings['password']}@{settings['server'][7:]}"
    with pytest.raises(ConnectionError, match="JP"):
        asyncio.run(go(country="JP"))


def test_proxy_url_keeps_the_pool_fresh(monkeypatch):
    from proxyscraper import api

    monkeypatch.setattr(api, "REFRESH_SECONDS", 0.05)
    runs = iter([agent.LiveList(rows=[row(1)], stats={**STATS, "updated": "run 1"}, loaded_at=0.0),
                 agent.LiveList(rows=[row(2)], stats={**STATS, "updated": "run 2"}, loaded_at=0.0)])

    class Source:  # the first call sees run 1, every later one run 2
        current = None

        async def get(self):
            self.current = next(runs, self.current)
            return self.current

    async def go():
        async with ProxyRotator(_source=Source(), _allow_private=True) as rotator:
            await rotator.aproxy_url()
            await asyncio.sleep(0.3)
            return {e.result.proxy for e in rotator._fetcher.server.pool.entries}
    assert asyncio.run(go()) == {row(2)["proxy"]}


def test_the_refresh_survives_a_surprise(monkeypatch):
    from proxyscraper import api

    monkeypatch.setattr(api, "REFRESH_SECONDS", 0.02)
    calls = []

    async def go():
        async with ProxyRotator(_source=source_for([row(1)]), _allow_private=True) as rotator:
            await rotator.aproxy_url()

            async def broken():
                calls.append(1)
                raise KeyError("stats")
            rotator._fetcher.refresh = broken
            await asyncio.sleep(0.2)
    asyncio.run(go())
    assert len(calls) > 2  # kept trying after the first failure
