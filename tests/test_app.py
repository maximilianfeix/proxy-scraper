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
