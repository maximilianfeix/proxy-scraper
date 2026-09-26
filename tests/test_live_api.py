"""live_proxies: the checked hourly list from Python, without running any checks."""

import asyncio
import json

import pytest

from proxyscraper import api, live_proxies

ROWS = [
    {"url": "socks5://1.1.1.1:1080", "proxy": "1.1.1.1:1080", "ptype": "socks5", "latency": 300, "exit_ip": "1.1.1.1",
     "https": True, "anonymity": "elite", "country": "DE", "asn": 1, "org": "A", "hosting": False,
     "blocklisted": False, "streak": 30, "uptime_7d": 95, "uptime_24h": 100, "first_seen": "2026-09-20T10:17:00+00:00"},
    {"url": "http://2.2.2.2:80", "proxy": "2.2.2.2:80", "ptype": "http", "latency": 100, "exit_ip": "2.2.2.2",
     "https": False, "anonymity": "anonymous", "country": "US", "hosting": True, "streak": 1, "uptime_7d": 4},
    {"url": "socks4://3.3.3.3:4145", "proxy": "3.3.3.3:4145", "ptype": "socks4", "latency": 200, "exit_ip": "3.3.3.3",
     "https": True, "anonymity": "elite", "country": "DE", "streak": 2},
]
STATS = {"updated": "2026-09-27T10:17:00+00:00", "run_hours": 1}


def fetch_from(payloads, calls=None):
    async def fetch(url, timeout=0, headers=None):
        if calls is not None:
            calls.append(url)
        return json.dumps(payloads[url.rsplit("/", 1)[1]]).encode()
    return fetch


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(api, "_live_fetch", fetch_from({"proxies.json": ROWS, "stats.json": STATS}))


def test_fastest_first_with_the_usual_fields():
    found = live_proxies()
    assert [p.url for p in found] == ["http://2.2.2.2:80", "socks4://3.3.3.3:4145", "socks5://1.1.1.1:1080"]
    best = found[2]
    assert (best.latency, best.country, best.https, best.anonymity) == (300, "DE", True, "elite")
    assert best.uptime_7d == 95 and best.first_seen.startswith("2026-09-20") and best.up_for_hours == 30
    assert found[1].uptime_7d is None  # older lists have no uptime yet


def test_same_filter_names_as_find_proxies():
    assert [p.url for p in live_proxies(types=["socks4", "socks5"], countries="de", https=True)] == [
        "socks4://3.3.3.3:4145", "socks5://1.1.1.1:1080"]
    assert [p.url for p in live_proxies(no_datacenter=True, anonymity="elite", min_uptime=90)] == [
        "socks5://1.1.1.1:1080"]
    assert [p.url for p in live_proxies(max_latency=250, limit=1)] == ["http://2.2.2.2:80"]


def test_anonymity_is_a_minimum_like_in_find_proxies():
    assert {p.url for p in live_proxies(anonymity="anonymous")} == {p["url"] for p in ROWS}


def test_bad_filters_raise_value_errors():
    with pytest.raises(ValueError, match="ftp"):
        live_proxies(types=["ftp"])
    with pytest.raises(ValueError):
        live_proxies(countries="Germany")


def test_async_version_works_inside_a_running_loop():
    async def go():
        return await api.live_proxies_async(types=["http"])
    assert [p.url for p in asyncio.run(go())] == ["http://2.2.2.2:80"]
