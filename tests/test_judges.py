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
    assert good is not None and good.ip == "127.0.0.1" and good.seen_ip == "203.0.113.7"
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
    watch, _used = make_watch(FakeProbes(down={"a", "b"}))
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
            self.on_ok()  # erste Kontrolle vor den Prüfungen war gut
            await asyncio.sleep(3600)

    watch = StubWatch()

    class OutageChecker:
        def __init__(self):
            self.calls = 0
            self.down = True

        async def check(self, key):
            self.calls += 1
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


def test_check_that_fails_after_the_switch_is_rechecked_not_counted(tmp_path):
    """Copilot-Fund: Eine Prüfung läuft noch mit dem alten Ziel, während gewechselt wird, und scheitert
    erst danach. Sie darf nicht als echter Fehlschlag in die Statistik – sie wird wiederholt."""
    jobs = ["http 1.1.1.1:80", "http 2.2.2.2:80"]
    switched = None  # asyncio.Event erst in der Loop anlegen (Python 3.9)

    class StubWatch:
        on_ok = on_switch = None

        async def run(self):
            self.on_ok()
            await asyncio.sleep(3600)

    watch = StubWatch()

    class SlowChecker:
        def __init__(self):
            self.seen = []

        async def check(self, key):
            self.seen.append(key)
            if key == "http 1.1.1.1:80" and not switched.is_set():
                await asyncio.sleep(0.05)      # noch unterwegs mit dem alten Ziel ...
                await switched.wait()
                return None                    # ... und scheitert erst nach dem Wechsel
            if key == "http 2.2.2.2:80" and not switched.is_set():
                watch.on_switch(JudgeProbe(Judge("a"), "1.1.1.1", 1), JudgeProbe(Judge("b"), "2.2.2.2", 1))
                switched.set()
            ptype, proxy = key.split(" ")
            return CheckResult(key, ptype, proxy, 100, "9.9.9.9")

        async def confirm(self, r):
            return True

        async def enrich(self, r):
            r.https = True

    checker = SlowChecker()

    async def go():
        nonlocal switched
        switched = asyncio.Event()
        stats = LiveStats({"http": len(jobs)})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 2, True)
        return await pipeline.run_checks(jobs, checker, RunOptions(no_geo=True, concurrency=2), dashboard, writer,
                                         GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext(),
                                         watch=watch)

    run = asyncio.run(go())
    assert checker.seen.count("http 1.1.1.1:80") == 2   # nach dem Wechsel erneut geprüft
    assert run.working == set(jobs) and sorted(run.checked) == sorted(jobs)
    assert run.rechecked == 1
    assert len(run.results) == 2                        # kein doppelter Treffer


def test_failures_before_the_last_good_probe_stay_counted(tmp_path):
    """Kontrolle ok -> ein paar echte Fehlschläge -> erneut ok -> Ausfall: nur was nach der zweiten
    guten Kontrolle scheiterte, wird wiederholt."""
    jobs = [f"http 1.1.1.{i}:80" for i in range(1, 7)]

    class StubWatch:
        on_ok = on_switch = None

        async def run(self):
            await asyncio.sleep(3600)

    watch = StubWatch()

    class Checker:
        calls = 0

        async def check(self, key):
            self.calls += 1
            if self.calls == 3:
                await asyncio.sleep(0.01)
                watch.on_ok()       # Prüfziel nach zwei echten Fehlschlägen noch erreichbar
                await asyncio.sleep(0.01)
            if self.calls == 5:
                watch.on_switch(JudgeProbe(Judge("a"), "1.1.1.1", 1), JudgeProbe(Judge("b"), "2.2.2.2", 1))
            return None             # alles scheitert – die ersten zwei aber vor der guten Kontrolle

        async def confirm(self, r):
            return True

    async def go():
        stats = LiveStats({"http": len(jobs)})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 1, True)
        return await pipeline.run_checks(jobs, Checker(), RunOptions(no_geo=True, concurrency=1), dashboard, writer,
                                         GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext(),
                                         watch=watch)

    run = asyncio.run(go())
    assert "http 1.1.1.1:80" in run.checked and "http 1.1.1.2:80" in run.checked  # echte Fehlschläge
    assert run.rechecked == 2  # 3 und 4 fielen in den Ausfall


def test_second_switch_only_rechecks_failures_under_the_new_target(tmp_path):
    """Nach einem Wechsel zählt die erfolgreiche Probe des neuen Ziels als gute Kontrolle: Fällt auch das
    aus, werden nur die Fehlschläge seit dem ersten Wechsel wiederholt – nicht die davor."""
    jobs = [f"http 1.1.1.{i}:80" for i in range(1, 7)]

    class StubWatch:
        on_ok = on_switch = None

        async def run(self):
            await asyncio.sleep(3600)

    watch = StubWatch()
    a, b, c = (JudgeProbe(Judge(h), "1.1.1.1", 1) for h in "abc")

    class Checker:
        calls = 0

        async def check(self, key):
            self.calls += 1
            await asyncio.sleep(0.01)
            if self.calls == 3:
                watch.on_switch(a, b)   # 1 und 2 fielen in den Ausfall von a
            await asyncio.sleep(0.01)
            if self.calls == 5:
                watch.on_switch(b, c)   # 4 fiel in den Ausfall von b (3 lief noch mit a)
            return None

        async def confirm(self, r):
            return True

    async def go():
        stats = LiveStats({"http": len(jobs)})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 1, True)
        return await pipeline.run_checks(jobs, Checker(), RunOptions(no_geo=True, concurrency=1), dashboard, writer,
                                         GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext(),
                                         watch=watch)

    run = asyncio.run(go())
    assert run.judge_switches == ["a → b", "b → c"]
    # 1, 2 (Ausfall a) + 3 (lief noch mit a, endete nach dem Wechsel) + 4, 5 (Ausfall b); danach ist die
    # Basislinie neu – die Wiederholungen unter c zählen normal
    assert sorted(set(run.checked)) == sorted(jobs) and len(run.checked) == len(jobs)


def test_a_single_cloudflare_address_rules_out_the_target(monkeypatch):
    async def fake_getaddrinfo(self, host, port, family=0, **kw):
        return [(2, 1, 6, "", ("34.251.184.218", port)), (2, 1, 6, "", ("104.16.184.241", port))]

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)
    assert asyncio.run(probe_judge(Judge("gemischt.example"), timeout=1)) is None


def test_own_ip_falls_back_to_what_the_judges_saw(monkeypatch):
    from proxyscraper import app
    from proxyscraper.judges import Judge as J

    async def no_own_ips():
        return []

    async def ranked():
        return [JudgeProbe(J("a"), "1.1.1.1", 10, "87.150.19.11"), JudgeProbe(J("b"), "2.2.2.2", 10, "87.150.19.11"),
                JudgeProbe(J("c"), "3.3.3.3", 10, "2003:d6::1")]  # IPv6 hilft dem Checker nicht

    async def no_confirm():
        return None

    monkeypatch.setattr(app, "get_own_ips", no_own_ips)
    monkeypatch.setattr(app, "rank_judges", ranked)
    monkeypatch.setattr(app, "confirm_target", no_confirm)
    run = app.Run(RunOptions(no_geo=True), show_banner=False)
    assert asyncio.run(run.prepare_network()) and run.own_ips == ["87.150.19.11"]
