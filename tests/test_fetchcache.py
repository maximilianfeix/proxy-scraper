"""ETag cache: unchanged lists come from the cache via 304 – against a real server on localhost."""

import asyncio
import time

import pytest

from proxyscraper import netio, pipeline
from proxyscraper import sources as srcs
from proxyscraper.fetchcache import FORGET_AFTER, FetchCache
from proxyscraper.ui import CollectView

LIST = b"socks5://8.8.4.4:1080\n1.1.1.1:80\n9.9.9.9:3128\n"


class ListServer:
    """Serves a proxy list with an ETag and answers a matching If-None-Match with 304."""

    def __init__(self, etag=b'"v1"'):
        self.etag = etag
        self.requests = []

    async def handle(self, reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        self.requests.append(head)
        if self.etag and b"If-None-Match: " + self.etag in head:
            writer.write(b"HTTP/1.1 304 Not Modified\r\nETag: " + self.etag + b"\r\n\r\n")
        else:
            etag = b"ETag: " + self.etag + b"\r\n" if self.etag else b""
            writer.write(b"HTTP/1.1 200 OK\r\n" + etag + b"Content-Length: %d\r\n\r\n" % len(LIST) + LIST)
        await writer.drain()
        writer.close()


def run_scrapes(tmp_path, server, runs, types=("http", "socks5"), between=None):
    """Several runs in a row with a shared cache/statistics; returns (results, views, stats)."""
    async def go():
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0)
        url = f"http://127.0.0.1:{srv.sockets[0].getsockname()[1]}/list.txt"
        quality = srcs.SourceStats(tmp_path / "stats.json")
        results, views = [], []
        try:
            for i in range(runs):
                if between and i:
                    between(tmp_path)
                cache = FetchCache(tmp_path / "cache")
                view = CollectView(1, time.perf_counter())
                results.append(await pipeline.scrape({url: "http"}, list(types), quality, view, cache))
                cache.save()
                views.append(view)
        finally:
            srv.close()
        return results, views, quality, url

    return asyncio.run(go())


def test_unchanged_list_comes_from_the_cache(tmp_path):
    server = ListServer()
    results, views, quality, url = run_scrapes(tmp_path, server, runs=2)
    first, second = results
    assert set(first.index) == set(second.index) == {"socks5 8.8.4.4:1080", "http 1.1.1.1:80", "http 9.9.9.9:3128"}
    assert (views[0].cached, views[1].cached) == (0, 1)
    assert views[1].bytes == 0
    assert b'If-None-Match: "v1"' in server.requests[1]
    rec = quality.get(url)
    assert rec.fail_streak == 0 and rec.count == 3  # 304 isn't a failure


def test_cache_is_unfiltered_so_types_can_change(tmp_path):
    server = ListServer()

    async def go():
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0)
        url = f"http://127.0.0.1:{srv.sockets[0].getsockname()[1]}/list.txt"
        quality = srcs.SourceStats(tmp_path / "stats.json")
        try:
            out = []
            for types in (["http"], ["socks5"]):
                cache = FetchCache(tmp_path / "cache")
                out.append(await pipeline.scrape({url: "http"}, types, quality, CollectView(1, 0), cache))
                cache.save()
            return out
        finally:
            srv.close()

    only_http, only_socks5 = asyncio.run(go())
    assert set(only_http.index) == {"http 1.1.1.1:80", "http 9.9.9.9:3128"}
    assert set(only_socks5.index) == {"socks5 8.8.4.4:1080"}  # from the cache, although http was asked for first


def test_broken_cache_file_triggers_a_normal_download(tmp_path):
    def break_cache(path):
        for f in (path / "cache").glob("*.gz"):
            f.write_bytes(b"not gzip")

    server = ListServer()
    results, views, _, _ = run_scrapes(tmp_path, server, runs=2, between=break_cache)
    assert len(results[1].index) == 3 and views[1].cached == 0
    assert len(server.requests) == 3  # 304 with a broken file -> once more without a condition


def test_servers_without_etag_are_not_cached(tmp_path):
    server = ListServer(etag=b"")
    _, views, _, _ = run_scrapes(tmp_path, server, runs=2)
    assert views[1].cached == 0 and b"If-None-Match" not in server.requests[1]


def test_no_cache_option_downloads_everything(tmp_path):
    cache = FetchCache(tmp_path / "cache", enabled=False)
    cache.store("http://x/list", {b"etag": b'"a"'}, "http 1.1.1.1:80", "http")
    assert cache.conditional_headers("http://x/list", "http") == {}
    assert not (tmp_path / "cache").exists()


def test_old_entries_are_forgotten(tmp_path):
    cache = FetchCache(tmp_path / "cache")
    cache.store("http://x/old", {b"last-modified": b"Mon, 01 Jan 2024 00:00:00 GMT"}, "http 1.1.1.1:80", "http")
    cache.store("http://x/new", {b"etag": b'"b"'}, "http 2.2.2.2:80", "http")
    expected = {"If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT"}
    assert cache.conditional_headers("http://x/old", "http") == expected
    cache.entries["http://x/old"]["used"] -= FORGET_AFTER + 1
    cache.save()
    again = FetchCache(tmp_path / "cache")
    assert list(again.entries) == ["http://x/new"]
    assert len(list((tmp_path / "cache").glob("*.gz"))) == 1


def test_unchanged_fetch_keeps_stale_detection_running():
    st = srcs.SourceStats.__new__(srcs.SourceStats)
    st.records = {}
    st.record_fetch("u", b"http 1.1.1.1:80", 1, now=1000)
    st.record_fetch("u", None, 0, now=1500)                  # unreachable once
    st.record_fetch("u", None, 0, now=2000, unchanged=True)  # 304, but nothing of the requested type
    rec = st.records["u"]
    assert rec.last_change == 1000 and rec.last_fetch == 2000 and rec.fail_streak == 0


def test_removed_last_entry_is_saved(tmp_path):
    cache = FetchCache(tmp_path / "cache")
    cache.store("http://x/list", {b"etag": b'"a"'}, "http 1.1.1.1:80", "http")
    cache.save()
    again = FetchCache(tmp_path / "cache")
    again.store("http://x/list", {}, "http 1.1.1.1:80", "http")  # the server no longer sends an ETag
    again.save()
    assert FetchCache(tmp_path / "cache").conditional_headers("http://x/list", "http") == {}


def test_changed_source_type_invalidates_the_entry(tmp_path):
    cache = FetchCache(tmp_path / "cache")
    cache.store("http://x/list", {b"etag": b'"a"'}, "http 1.1.1.1:80", "http")
    assert cache.conditional_headers("http://x/list", "http") == {"If-None-Match": '"a"'}
    assert cache.conditional_headers("http://x/list", "socks5") == {}


@pytest.mark.parametrize("method, headers, body, allowed", [
    ("GET", None, None, True),                                  # public list
    ("GET", {"If-None-Match": '"a"'}, None, True),              # conditional fetch for the cache
    ("GET", {"Authorization": "token x"}, None, False),         # GitHub-Token
    ("POST", {"If-None-Match": '"a"'}, b"secret", False),       # never send data unverified
    ("POST", None, b"secret", False),                           # not even without any headers
    ("GET", {"If-None-Match": '"a"', "Authorization": "x"}, None, False),
])
def test_unverified_tls_only_for_requests_without_secrets(monkeypatch, method, headers, body, allowed):
    seen = []

    async def fake_connect(host, port, https, allow_insecure, timeout):
        seen.append(allow_insecure)
        raise ConnectionError("only the call matters")

    monkeypatch.setattr(netio, "_connect", fake_connect)
    with pytest.raises(ConnectionError):
        asyncio.run(netio.http_request("https://example.com/list.txt", headers=headers, method=method, body=body))
    assert seen == [allowed]


def test_corrupt_deflate_data_is_a_cache_miss(tmp_path):
    import gzip
    cache = FetchCache(tmp_path / "cache")
    cache.store("http://x/list", {b"etag": b'"a"'}, "http 1.1.1.1:80", "http")
    path = tmp_path / "cache" / cache.entries["http://x/list"]["file"]
    data = bytearray(gzip.compress(b"http 1.1.1.1:80\n" * 200))
    data[20:40] = b"\xff" * 20  # valid gzip header, broken data -> zlib.error
    path.write_bytes(bytes(data))
    assert cache.load("http://x/list") is None


def test_dropping_validators_removes_the_payload(tmp_path):
    cache = FetchCache(tmp_path / "cache")
    cache.store("http://x/list", {b"etag": b'"a"'}, "http 1.1.1.1:80", "http")
    cache.store("http://x/list", {}, "http 1.1.1.1:80", "http")
    assert list((tmp_path / "cache").glob("*.gz")) == []


@pytest.mark.parametrize("index", ['[1, 2, 3]', '{"http://x/l": {"etag": "a"}}', '{"http://x/l": "kaputt"}',
                                   '{"http://x/l": {"file": "../../etc/passwd", "etag": "a"}}'])
def test_malformed_index_is_an_empty_cache(tmp_path, index):
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "index.json").write_text(index)
    cache = FetchCache(tmp_path / "cache")
    assert cache.entries == {} and cache.conditional_headers("http://x/l", "http") == {}
    cache.save()  # must not trip either
