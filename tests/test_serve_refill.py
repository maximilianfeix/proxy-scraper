"""--serve-refill: the running proxy server picks up fresh proxies in the background (#109)."""

import asyncio
import contextlib

from proxyscraper import app, output, pipeline
from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.geo import GeoResolver
from proxyscraper.options import Filters, RunOptions
from proxyscraper.pipeline import CheckRun
from proxyscraper.server import ProxyPool, RotatingServer
from proxyscraper.ui.dashboard import CheckDashboard, LiveStats


def hit(n, latency=100, country="DE", https=True):
    return CheckResult(f"http 1.1.1.{n}:80", "http", f"1.1.1.{n}:80", latency, "9.9.9.9", https=https,
                       country=country)


def test_merge_adds_new_revives_known_and_drops_the_dead():
    pool = ProxyPool([hit(1), hit(2), hit(3)])
    alive, came_back, dead = pool.entries
    alive.ok = 7
    came_back.disabled = dead.disabled = True
    added = pool.merge([hit(2, latency=50), hit(4), hit(1, latency=90)])
    assert added == 1
    keys = [e.result.key for e in pool.entries]
    assert keys == ["http 1.1.1.2:80", "http 1.1.1.1:80", "http 1.1.1.4:80"]  # fastest first, 3 dropped
    assert not came_back.disabled and came_back.result.latency == 50  # fresh result, back in the rotation
    assert alive.ok == 7  # counters of known proxies stay


def test_options_roundtrip():
    for argv in (["--serve", "--serve-refill", "6"], ["--serve", "--serve-refill", "0.5"]):
        opts = RunOptions.from_args(parse_args(argv))
        assert RunOptions.from_args(parse_args(opts.to_argv())) == opts
    assert RunOptions.from_args(parse_args(["--serve-refill", "6"])).to_argv() == ["--serve-refill", "6"]
    assert "--serve-refill" not in RunOptions().to_argv()


def test_refill_checks_quietly_and_merges_what_passes_the_filters(monkeypatch, tmp_path):
    seen = {}

    async def fake_run_checks(jobs, checker, opts, dashboard, writer, geo, **kw):
        seen.update(jobs=jobs, quiet=kw.get("quiet"), concurrency=opts.concurrency)
        run = CheckRun()
        for r in (hit(5), hit(6, country="US")):
            run.results.append(r)
            run.working.add(r.key)
            run.checked.append(r.key)
        run.checked.append("http 1.1.1.7:80")
        return run

    async def live_jobs(types, history, fetch=None):
        return ["http 1.1.1.1:80", "http 1.1.1.5:80", "http 1.1.1.6:80", "http 1.1.1.7:80"]

    class Checker:
        unreachable = {"1.1.1.5:80"}

    monkeypatch.setattr(app, "run_checks", fake_run_checks)
    monkeypatch.setattr(app, "load_live_jobs", live_jobs)
    monkeypatch.setattr(output, "RESULTS_DIR", tmp_path)
    learned = []
    monkeypatch.setattr(app.Run, "learn", lambda self, run, blocked, sources=True: learned.append(sources))

    run = app.Run(RunOptions(recheck="live", no_geo=True, serve_refill=6, filters=Filters(countries=["DE"])))
    run.checker = Checker()
    pool = ProxyPool([hit(1)])
    added = asyncio.run(run.refill(pool))

    assert seen["jobs"] == ["http 1.1.1.5:80", "http 1.1.1.6:80", "http 1.1.1.7:80"]  # 1 is serving already
    assert seen["quiet"] is True and seen["concurrency"] == app.REFILL_CONCURRENCY
    assert added == 1 and [e.result.key for e in pool.entries] == ["http 1.1.1.1:80", "http 1.1.1.5:80"]  # US filtered
    assert learned == [False]  # history yes, source ranking no
    assert run.checker.unreachable == set()  # hours later, down addresses get another chance
    assert (tmp_path / "latest").exists() or (tmp_path / "latest.txt").exists()  # --recheck later sees the refill


def test_quiet_run_checks_leaves_ctrl_c_alone(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise AssertionError("quiet mode must not take over Ctrl+C")

    monkeypatch.setattr(pipeline, "on_interrupt", boom)

    class Checker:
        async def check(self, key):
            return None

    async def go():
        stats = LiveStats({"http": 1})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        return await pipeline.run_checks(["http 1.1.1.1:80"], Checker(), RunOptions(no_geo=True, concurrency=1),
                                         CheckDashboard(stats, writer.live_path, 1, True), writer,
                                         GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext(),
                                         quiet=True)

    assert asyncio.run(go()).checked == ["http 1.1.1.1:80"]


def test_keep_refilling_survives_a_failed_round(monkeypatch):
    rounds = []

    async def refill(self, pool):
        rounds.append(1)
        if len(rounds) == 1:
            raise OSError("live list unreachable")
        return 3

    monkeypatch.setattr(app.Run, "refill", refill)
    monkeypatch.setattr(app, "note", lambda *a, **k: None)
    server = RotatingServer(ProxyPool([hit(1)]))

    async def go():
        task = asyncio.ensure_future(app.Run(RunOptions()).keep_refilling(server, 0.01))
        while len(rounds) < 3:
            await asyncio.sleep(0.01)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert server.refilled >= 3 and server.last_refill
