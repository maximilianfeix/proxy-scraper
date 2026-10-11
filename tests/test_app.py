import asyncio

import pytest

from proxyscraper import app


@pytest.mark.parametrize("probe_ok, expected", [(True, "34.1.2.3"), (False, None)])
def test_confirm_target_probes_the_resolved_ip(monkeypatch, probe_ok, expected):
    probed = []

    async def fake_probe(ip, timeout):
        probed.append(ip)
        return probe_ok

    async def go():
        loop = asyncio.get_running_loop()

        async def fake_getaddrinfo(*args, **kwargs):
            return [(None, None, None, "", ("34.1.2.3", 80))]

        monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
        return await app.confirm_target()

    monkeypatch.setattr(app, "probe_confirm_target", fake_probe)
    assert asyncio.run(go()) == expected
    assert probed == ["34.1.2.3"]  # exactly the IP that is used later


def test_confirm_target_unresolvable(monkeypatch):
    async def go():
        loop = asyncio.get_running_loop()

        async def fail(*args, **kwargs):
            raise OSError("no name resolution")

        monkeypatch.setattr(loop, "getaddrinfo", fail)
        return await app.confirm_target()

    assert asyncio.run(go()) is None


@pytest.mark.parametrize("found, fakes, expected", [
    (0, 0, True),      # nothing gets through -> firewall
    (1, 0, True),
    (0, 50, False),    # honeypots pass the basic check -> connections work
    (30, 0, False),
])
def test_network_blocked_counts_fakes_as_reachable(found, fakes, expected):
    from proxyscraper.ui import LiveStats

    stats = LiveStats({"http": 10000})
    stats.checked = 10000
    stats.working_by_type["http"] = found
    stats.fakes = fakes
    assert app.is_network_blocked(stats) is expected


def test_recheck_live_loads_the_public_list(tmp_path):
    from proxyscraper import app
    from proxyscraper.history import ProxyHistory

    async def fetch(url, timeout):
        assert url.endswith("/proxy-list/all.txt")
        return b"socks5://8.8.4.4:1080\nhttp://1.1.1.1:80\nkaputt\n"

    history = ProxyHistory(tmp_path / "h.json")
    jobs = asyncio.run(app.load_live_jobs(["socks5", "http"], history, fetch=fetch))
    assert jobs == ["socks5 8.8.4.4:1080", "http 1.1.1.1:80"]
    assert asyncio.run(app.load_live_jobs(["http"], history, fetch=fetch)) == ["http 1.1.1.1:80"]


def test_recheck_live_falls_back_when_offline(tmp_path, monkeypatch):
    from proxyscraper import app
    from proxyscraper.history import ProxyHistory

    async def fetch(url, timeout):
        raise ConnectionError("offline")

    monkeypatch.setattr(app, "latest_results", lambda: ["http://9.9.9.9:80"])
    monkeypatch.setattr(app, "note", lambda *a, **k: None)
    jobs = asyncio.run(app.load_live_jobs(["http"], ProxyHistory(tmp_path / "h.json"), fetch=fetch))
    assert jobs == ["http 9.9.9.9:80"]


def test_recheck_url_downloads_and_reads_the_list_like_stdin():
    from proxyscraper import app

    async def fetch(url, timeout):
        assert url == "https://example.com/proxies.txt" and timeout == 30
        return b"socks5://8.8.4.4:1080\n1.1.1.1:80\n| 9.9.9.9 | 3128 |\n"

    jobs = asyncio.run(app.load_url_jobs("https://example.com/proxies.txt", ["http", "socks5"], fetch=fetch))
    assert jobs == ["socks5 8.8.4.4:1080", "http 1.1.1.1:80", "socks5 1.1.1.1:80", "http 9.9.9.9:3128",
                    "socks5 9.9.9.9:3128"]
    assert asyncio.run(app.load_url_jobs("https://example.com/proxies.txt", ["socks5"], fetch=fetch)) == [
        "socks5 8.8.4.4:1080", "socks5 1.1.1.1:80", "socks5 9.9.9.9:3128"]


def test_recheck_url_keeps_logins_behind_a_bom():
    from proxyscraper import app

    async def fetch(url, timeout):  # a list saved by Notepad or PowerShell starts with a BOM
        return b"\xef\xbb\xbfuser:pass@8.8.8.8:8080\n9.9.9.9:3128:user:pass\n"

    jobs = asyncio.run(app.load_url_jobs("https://example.com/bought.txt", ["http"], fetch=fetch))
    # ip:port:user:pass keeps its login, and the bare address stays too – "ip:port:US:elite" looks the same
    assert jobs == ["http user:pass@8.8.8.8:8080", "http user:pass@9.9.9.9:3128", "http 9.9.9.9:3128"]


def test_recheck_url_errors_reach_the_caller():
    from proxyscraper import app

    async def fetch(url, timeout):
        raise ConnectionError("HTTP 404")

    with pytest.raises(ConnectionError):
        asyncio.run(app.load_url_jobs("https://example.com/gone.txt", ["http"], fetch=fetch))


@pytest.mark.parametrize("target, expected", [
    ("https://example.com/a.txt", True), ("HTTP://x", True), ("proxies.txt", False), ("-", False), ("", False),
    ("live", False),
])
def test_is_url(target, expected):
    from proxyscraper import app

    assert app.is_url(target) is expected
