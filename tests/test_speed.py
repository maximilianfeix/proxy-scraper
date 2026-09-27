"""Download speed per proxy: 100 KB through each HTTPS-capable proxy, with a hard deadline."""

import asyncio
import json

from proxyscraper import speed


def test_rate_from_bytes_and_time():
    assert speed.kbps(100_000, 0.5) == 195          # 100 KB in half a second
    assert speed.kbps(30_000, 12.0) == 2            # a trickle: still a real (slow) measurement
    assert speed.kbps(5_000, 1.0) is None           # too little to say anything


def run_dir(tmp_path, rows):
    d = tmp_path / "run"
    d.mkdir()
    (d / "proxies.json").write_text(json.dumps(rows))
    return d


def row(n, https=True):
    return {"url": f"socks5://1.1.1.{n}:1080", "ptype": "socks5", "proxy": f"1.1.1.{n}:1080", "https": https,
            "latency": 100}


def test_only_https_proxies_are_measured_and_failures_leave_no_value(tmp_path):
    measured = []

    async def probe(r, ip):
        measured.append(r["proxy"])
        return None if r["proxy"].endswith(".2:1080") else 850

    d = run_dir(tmp_path, [row(1), row(2), row(3, https=False)])
    median = asyncio.run(speed.fill_run(d, probe=probe, resolve=lambda host: "10.0.0.1"))
    rows = {r["proxy"]: r for r in json.loads((d / "proxies.json").read_text())}
    assert rows["1.1.1.1:1080"]["speed_kbps"] == 850
    assert "speed_kbps" not in rows["1.1.1.2:1080"] and "speed_kbps" not in rows["1.1.1.3:1080"]
    assert sorted(measured) == ["1.1.1.1:1080", "1.1.1.2:1080"] and median == 850


def test_the_deadline_holds_for_proxies_that_never_finish(tmp_path, monkeypatch):
    monkeypatch.setattr(speed, "DEADLINE", 0.2)

    async def probe(r, ip):
        await asyncio.sleep(30)  # the probe itself has its own deadline; this is the belt to those braces
        return 1

    d = run_dir(tmp_path, [row(1)])

    async def go():
        return await asyncio.wait_for(speed.fill_run(d, probe=probe, resolve=lambda host: "10.0.0.1"), 5)
    asyncio.run(go())
    assert "speed_kbps" not in json.loads((d / "proxies.json").read_text())[0]


# --------------------------------------------------------------------------- where the speed shows up

def test_publish_keeps_the_speed_and_its_median(tmp_path):
    from proxyscraper import publish
    from tests.test_publish import run_dir as publish_run
    d = publish_run(tmp_path)
    rows = json.loads((d / "proxies.json").read_text())
    for i, r in enumerate(rows):
        if r.get("https"):
            r["speed_kbps"] = 100 * (i + 1)
    (d / "proxies.json").write_text(json.dumps(rows))
    out = tmp_path / "public"
    publish.publish(d, out, minimum=2)
    stats = json.loads((out / "stats.json").read_text())
    assert stats["median_speed_kbps"] > 0
    assert "speed_kbps" in (out / "proxies.csv").read_text().splitlines()[0]


def test_filters_by_speed_for_agents_and_python(monkeypatch):
    from proxyscraper import agent, api
    rows = [{"url": "http://1.1.1.1:80", "ptype": "http", "proxy": "1.1.1.1:80", "latency": 1, "speed_kbps": 900},
            {"url": "http://2.2.2.2:80", "ptype": "http", "proxy": "2.2.2.2:80", "latency": 2, "speed_kbps": 50},
            {"url": "http://3.3.3.3:80", "ptype": "http", "proxy": "3.3.3.3:80", "latency": 3}]
    assert [r["url"] for r in agent.select(rows, min_speed_kbps=500)] == ["http://1.1.1.1:80"]
    assert agent.describe(rows[0])["speed_kbps"] == 900
    from tests.test_live_api import STATS, fetch_from
    monkeypatch.setattr(api, "_live_fetch", fetch_from({"proxies.json": rows, "stats.json": STATS}))
    found = api.live_proxies(min_speed=100)
    assert [p.url for p in found] == ["http://1.1.1.1:80"] and found[0].speed_kbps == 900


def test_a_body_that_is_already_buffered_is_not_absurdly_fast(monkeypatch):
    # the whole body arrives with the head: the clock must not start after it's already there
    import time as time_mod

    class Reader:
        def __init__(self):
            self.parts = [b"HTTP/1.1 200 OK\r\n\r\n", b"x" * 65536, b"x" * (speed.BYTES - 65536), b""]

        async def readuntil(self, sep):
            return self.parts.pop(0)

        async def read(self, n):
            return self.parts.pop(0)

    class Writer:
        def write(self, data):
            pass

        async def drain(self):
            clock[0] += 0.5  # the proxy takes half a second to answer

        def close(self):
            pass

    clock = [100.0]
    monkeypatch.setattr(time_mod, "monotonic", lambda: clock[0])

    async def tunnel(*a, **k):
        return Reader(), Writer()

    from proxyscraper import checker
    monkeypatch.setattr(checker.Checker, "_tls_tunnel", lambda self, *a, **k: tunnel())
    rate = asyncio.run(speed.real_probe()({"ptype": "socks5", "proxy": "1.1.1.1:1080"}, "10.0.0.1"))
    assert rate == speed.kbps(speed.BYTES, 0.5)  # 100 KB in the half second it took, not in 0 s
