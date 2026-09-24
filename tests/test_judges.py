"""Prüfziele: Auswahl, Cloudflare-Sperre, Wechsel bei Ausfall und was das für die Statistik heißt."""

import asyncio
import contextlib

import pytest

from proxyscraper import checker as ck
from proxyscraper import output, pipeline
from proxyscraper.checker import CheckResult
from proxyscraper.geo import GeoResolver
from proxyscraper.judges import Judge, JudgeProbe, JudgeWatch, behind_cloudflare, probe_judge, rank_judges
from proxyscraper.options import RunOptions
from proxyscraper.ui import CheckDashboard, LiveStats


@pytest.mark.parametrize("ip, expected", [
    ("104.16.184.241", True),    # icanhazip.com
    ("172.67.74.152", True),     # api.ipify.org
    ("34.251.184.218", False),   # checkip.amazonaws.com
    ("65.108.151.63", False),
])
def test_cloudflare_detection(ip, expected):
    assert behind_cloudflare(ip) is expected


async def ip_echo(reader, writer):
    head = await reader.readuntil(b"\r\n\r\n")
    body = b"203.0.113.7\n" if head.startswith(b"GET /ip ") else b"<html>nope</html>"
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
    await writer.drain()
    writer.close()


def test_probe_accepts_only_a_bare_ip():
    async def go():
        srv = await asyncio.start_server(ip_echo, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        try:
            return (await probe_judge(Judge("127.0.0.1", "/ip", port), timeout=2),
                    await probe_judge(Judge("127.0.0.1", "/", port), timeout=2),
                    await probe_judge(Judge("127.0.0.1", "/ip", 1), timeout=2))
        finally:
            srv.close()

    good, html, dead = asyncio.run(go())
    assert good is not None and good.ip == "127.0.0.1"
    assert html is None and dead is None


def test_rank_keeps_the_preference_order_and_drops_unreachable():
    judges = [Judge("a"), Judge("b"), Judge("c")]

    async def probe(judge, timeout):
        # "b" antwortet am schnellsten, "a" ist aber das bessere Ziel – Reihenfolge bleibt
        return None if judge.host == "c" else JudgeProbe(judge, "1.1.1.1", {"a": 300, "b": 50}[judge.host])

    ranked = asyncio.run(rank_judges(judges, probe=probe))
    assert [r.judge.host for r in ranked] == ["a", "b"]


class FakeProbes:
    def __init__(self, down=()):
        self.down = set(down)

    async def __call__(self, judge, timeout=5.0):
        return None if judge.host in self.down else JudgeProbe(judge, "2.2.2.2", 100)


def make_watch(probes, hosts=("a", "b", "c")):
    ranked = [JudgeProbe(Judge(h), "1.1.1.1", 100) for h in hosts]
    used = []
    watch = JudgeWatch(ranked, used.append, probe=probes)
    return watch, used


def test_watch_needs_two_failures_before_switching():
    probes = FakeProbes(down={"a"})
    watch, used = make_watch(probes)
    asyncio.run(watch.check_once())
    assert used == [] and watch.current.judge.host == "a"
    asyncio.run(watch.check_once())
    assert [p.judge.host for p in used] == ["b"] and watch.switches == ["a → b"]


def test_watch_skips_reserves_that_are_down_too():
    watch, used = make_watch(FakeProbes(down={"a", "b"}))
    for _ in range(2):
        asyncio.run(watch.check_once())
    assert watch.current.judge.host == "c"
    assert [r.judge.host for r in watch.reserve] == ["b", "a"]  # das ausgefallene kommt ans Ende


def test_watch_recovers_after_a_single_hiccup():
    probes = FakeProbes(down={"a"})
    watch, used = make_watch(probes)
    asyncio.run(watch.check_once())
    probes.down.clear()
    asyncio.run(watch.check_once())
    asyncio.run(watch.check_once())
    assert used == [] and watch.failures == 0


def test_checker_can_switch_judge_mid_run():
    c = ck.Checker("1.2.3.4", set(), timeout=1, connect_timeout=1)
    assert b"Host: checkip.amazonaws.com\r\n" in c.request
    c.use_judge(Judge("ifconfig.me", "/ip"), "34.160.111.145")
    assert c.request.startswith(b"GET /ip HTTP/1.1\r\nHost: ifconfig.me\r\n")
    assert c.http_proxy_request.startswith(b"GET http://ifconfig.me/ip HTTP/1.1\r\n")
    assert c.judge_ip_bytes == bytes([34, 160, 111, 145])


def test_outage_mid_run_rechecks_and_keeps_stats_clean(tmp_path):
    """Die ersten drei Prüfungen fallen in einen Ausfall des Prüfziels. Nach dem Wechsel werden genau
    diese drei wiederholt; für die Statistik zählt jeder Proxy nur einmal."""
    jobs = [f"http 1.1.1.{i}:80" for i in range(1, 7)]

    class StubWatch:
        on_ok = on_switch = None

        async def run(self):
            await asyncio.sleep(3600)

    watch = StubWatch()

    class OutageChecker:
        def __init__(self):
            self.calls = 0
            self.down = True

        async def check(self, key):
            self.calls += 1
            if self.calls == 1:
                watch.on_ok()                  # Kontrolle vor dem Ausfall war noch gut
            if self.down and self.calls > 3:  # Watchdog bemerkt den Ausfall und wechselt
                self.down = False
                watch.on_switch(JudgeProbe(Judge("a"), "1.1.1.1", 1), JudgeProbe(Judge("b"), "2.2.2.2", 1))
            if self.down:
                return None
            ptype, proxy = key.split(" ")
            return CheckResult(key, ptype, proxy, 100, "9.9.9.9")

        async def confirm(self, r):
            return True

        async def enrich(self, r):
            r.https = True

    async def go():
        stats = LiveStats({"http": len(jobs)})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 1, True)
        opts = RunOptions(no_geo=True, concurrency=1)
        run = await pipeline.run_checks(jobs, OutageChecker(), opts, dashboard, writer, GeoResolver(enabled=False),
                                        live_factory=lambda _: contextlib.nullcontext(), watch=watch)
        return run, stats, dashboard

    run, stats, dashboard = asyncio.run(go())
    assert run.working == set(jobs)            # alle sechs funktionieren nach dem Wechsel
    assert sorted(run.checked) == sorted(jobs)  # jeder genau einmal – keine falschen Fehlschläge
    assert run.rechecked == 3 and run.judge_switches == ["a → b"]
    assert stats.total == 9 and stats.total_by_type["http"] == 9
    assert "b" in dashboard.judge_note
