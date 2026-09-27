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
