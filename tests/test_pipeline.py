import json

import pytest

from proxyscraper import output, pipeline
from proxyscraper import sources as srcs
from proxyscraper.checker import CheckResult
from proxyscraper.geo import flag
from proxyscraper.history import MAX_FAIL_STREAK, ProxyHistory
from proxyscraper.ui import bar, fmt, pct


def result(key="http 1.1.1.1:80", latency=500, https=True, anonymity="elite", country="DE"):
    ptype, proxy = key.split(" ")
    return CheckResult(key, ptype, proxy, latency, "9.9.9.9", https, anonymity, country)


def test_attribute_results_counts_per_source():
    res = pipeline.ScrapeResult(["a", "b"], {"http 1.1.1.1:80": [0, 1], "http 2.2.2.2:80": [1]})
    out = pipeline.attribute_results(res, ["http 1.1.1.1:80", "http 2.2.2.2:80"], {"http 1.1.1.1:80"})
    assert out == {"a": (1, 1), "b": (2, 1)}


def test_prioritize_history_first_then_good_sources(tmp_path):
    quality = srcs.SourceStats(tmp_path / "stats.json")
    quality.record_checks({"good": (100, 50), "bad": (100, 0)})
    history = ProxyHistory(tmp_path / "h.json")
    history.record_ok("socks5 7.7.7.7:1080", 100, "7.7.7.7")
    history.record_ok("socks4 8.8.8.8:1080", 100, "8.8.8.8")  # type not requested
    res = pipeline.ScrapeResult(["bad", "good"], {"http 1.1.1.1:80": [0], "http 2.2.2.2:80": [1]})
    order = pipeline.prioritize(res, quality, history, ["http", "socks5"])
    assert order == ["socks5 7.7.7.7:1080", "http 2.2.2.2:80", "http 1.1.1.1:80"]


def test_best_sources_needs_minimum_sample():
    per = {"a": (100, 10), "b": (10, 5), "c": (50, 0)}
    assert [u for *_, u in pipeline.best_sources(per)] == ["a"]


def test_history_reliability_and_pruning(tmp_path):
    h = ProxyHistory(tmp_path / "h.json")
    h.record_ok("http 1.1.1.1:80", 300, "1.1.1.1", now=1000.0, country="DE", https=True)
    h.record_ok("http 2.2.2.2:80", 300, "2.2.2.2", now=1000.0)
    for _ in range(MAX_FAIL_STREAK):
        h.record_fail("http 2.2.2.2:80")
    h.record_fail("http 3.3.3.3:80")  # unknown -> isn't created
    assert h.ranked_keys()[0] == "http 1.1.1.1:80"
    assert h.prune(now=1001.0) == 1
    h.save()
    again = ProxyHistory(tmp_path / "h.json")
    assert list(again.records) == ["http 1.1.1.1:80"]
    assert again.get("http 1.1.1.1:80").country == "DE"


def test_result_writer_creates_all_formats(tmp_path):
    w = output.ResultWriter(run_dir=tmp_path / "run1", extra_file=tmp_path / "extra.txt")
    rows = [result("socks5 2.2.2.2:1080", 900), result("http 1.1.1.1:80", 200)]
    w.add_live(rows[0])
    files = w.finalize(rows)
    run = tmp_path / "run1"
    assert (run / "all.txt").read_text() == "http://1.1.1.1:80\nsocks5://2.2.2.2:1080\n"
    assert (run / "socks5.txt").read_text() == "2.2.2.2:1080\n"
    assert json.loads((run / "proxies.json").read_text())[0]["url"] == "http://1.1.1.1:80"
    assert (run / "proxies.csv").read_text().splitlines()[0].startswith("ptype,proxy,latency")
    assert (tmp_path / "extra.txt").exists()
    assert len(files) == 6  # all, http, socks5, json, csv, -o
    assert output.latest_run_dir(tmp_path) == run
    assert output.latest_results(tmp_path) == ["http://1.1.1.1:80", "socks5://2.2.2.2:1080"]


def test_latest_pointer_works_without_symlinks(tmp_path, monkeypatch):
    def no_symlinks(*args, **kwargs):
        raise OSError("symbolic links not permitted")  # Windows without admin/developer rights

    monkeypatch.setattr(output.os, "symlink", no_symlinks)
    for name in ("run1", "run2"):
        w = output.ResultWriter(run_dir=tmp_path / name)
        w.finalize([result(f"http 1.1.1.{len(name)}:80")])
    assert not (tmp_path / "latest").exists()
    assert output.latest_run_dir(tmp_path) == tmp_path / "run2"


@pytest.mark.parametrize("content", ["", "\n", "..", "../elsewhere", "run1/../..", "does-not-exist"])
def test_invalid_latest_pointer_is_ignored(tmp_path, content):
    (tmp_path / "run1").mkdir()
    (tmp_path / output.LATEST_POINTER).write_text(content)
    assert output.latest_run_dir(tmp_path) is None


def test_unreadable_latest_pointer_falls_back_to_symlink(tmp_path):
    (tmp_path / "run1").mkdir()
    (tmp_path / output.LATEST_POINTER).write_bytes(b"\xff\xfe kaputt")
    assert output.latest_run_dir(tmp_path) is None
    try:
        (tmp_path / "latest").symlink_to("run1", target_is_directory=True)
    except OSError:
        pytest.skip("no symlinks allowed")
    assert output.latest_run_dir(tmp_path) == tmp_path / "latest"


def test_latest_results_empty_without_runs(tmp_path):
    assert output.latest_run_dir(tmp_path) is None
    assert output.latest_results(tmp_path) == []
    assert not output.has_latest_results(tmp_path)


def test_has_latest_results(tmp_path):
    w = output.ResultWriter(run_dir=tmp_path / "run1")
    w.finalize([])
    assert not output.has_latest_results(tmp_path)  # run without hits
    w = output.ResultWriter(run_dir=tmp_path / "run2")
    w.finalize([result()])
    assert output.has_latest_results(tmp_path)


def test_history_exists(tmp_path):
    path = tmp_path / "h.json"
    assert not ProxyHistory.exists(path)
    path.write_text("{}")
    assert not ProxyHistory.exists(path)
    h = ProxyHistory(path)
    h.record_ok("http 1.1.1.1:80", 100, "1.1.1.1")
    h.save()
    assert ProxyHistory.exists(path)


def test_ui_helpers():
    assert fmt(1234567) == "1,234,567"
    assert pct(1, 3) == "33.3%" and pct(1, 0) == "–"
    assert bar(5, 10, 4, "green").plain == "██··"
    assert flag("DE") == "🇩🇪" and flag("") == "  "


def test_console_is_swappable_everywhere(monkeypatch):
    """All output goes through widgets.console – no frozen copy through an import."""
    import io

    from rich.console import Console

    from proxyscraper import app, cli
    from proxyscraper import pipeline as pipeline_module
    from proxyscraper.ui import widgets

    recorder = Console(file=io.StringIO(), width=80)
    monkeypatch.setattr(widgets, "console", recorder)
    for module in (app, cli, pipeline_module):
        assert getattr(module, "console", None) is None, module.__name__
    widgets.info("Test", "running")
    assert "running" in recorder.file.getvalue()


def test_card_subtitle_stays_on_one_line():
    import io

    from rich.console import Console

    from proxyscraper.ui.widgets import card

    console = Console(width=24, file=io.StringIO(), color_system=None)
    console.print(card("Saved", "12", "HTTPS only · min. anonymous · ≤ 3000 ms"))
    assert len(console.file.getvalue().splitlines()) == 5  # border, 3 lines, border


def test_run_checks_drops_unconfirmed_proxies(tmp_path):
    import asyncio
    import contextlib

    from proxyscraper.geo import GeoResolver
    from proxyscraper.options import RunOptions
    from proxyscraper.ui import CheckDashboard, LiveStats

    class StubChecker:
        async def check(self, key):
            ptype, proxy = key.split(" ")
            return CheckResult(key, ptype, proxy, 100, "9.9.9.9")

        async def confirm(self, r):
            return r.proxy.startswith("1.")  # 2.x.x.x is a "honeypot"

        async def tampers(self, r):
            return False

        async def enrich(self, r):
            r.https = True

    async def go():
        jobs = ["http 1.1.1.1:80", "http 2.2.2.2:80"]
        stats = LiveStats({"http": 2})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 2, True)
        run = await pipeline.run_checks(jobs, StubChecker(), RunOptions(no_geo=True), dashboard, writer,
                                        GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext())
        return run, stats, writer

    run, stats, writer = asyncio.run(go())
    assert [r.key for r in run.results] == ["http 1.1.1.1:80"]
    assert run.working == {"http 1.1.1.1:80"}
    assert stats.fakes == 1 and stats.found == 1
    assert writer.live_path.read_text(encoding="utf-8") == "http://1.1.1.1:80\n"


def test_anonymity_is_counted_without_https_test():
    from proxyscraper.ui import LiveStats

    stats = LiveStats({"http": 1})
    stats.add_working(result(anonymity="elite"))  # comes from the confirmation, also with --fast
    assert stats.anonymity["elite"] == 1 and stats.https_ok == 0


def test_run_checks_skips_https_test_when_filters_already_fail(tmp_path):
    import asyncio
    import contextlib

    from proxyscraper.geo import GeoResolver
    from proxyscraper.options import Filters, RunOptions
    from proxyscraper.ui import CheckDashboard, LiveStats

    enriched = []

    class StubChecker:
        async def check(self, key):
            ptype, proxy = key.split(" ")
            return CheckResult(key, ptype, proxy, 100, "9.9.9.9")

        async def confirm(self, r):
            r.anonymity = "elite" if r.proxy.startswith("1.") else "anonymous"
            return True

        async def tampers(self, r):
            return False

        async def enrich(self, r):
            enriched.append(r.key)
            r.https = True

    async def go():
        stats = LiveStats({"http": 2})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        opts = RunOptions(no_geo=True, filters=Filters(min_anonymity="elite"))
        await pipeline.run_checks(["http 1.1.1.1:80", "http 2.2.2.2:80"], StubChecker(), opts,
                                  CheckDashboard(stats, writer.live_path, 2, True), writer,
                                  GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext())
        return stats

    stats = asyncio.run(go())
    assert enriched == ["http 1.1.1.1:80"]   # the proxy that is only "anonymous" needs no HTTPS test
    assert stats.details_saved == 1 and stats.found == 2
