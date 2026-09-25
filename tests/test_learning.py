"""Learning fixes from the package review (#83)."""

import asyncio
import contextlib

from proxyscraper import output, pipeline
from proxyscraper import sources as srcs
from proxyscraper.checker import CheckResult
from proxyscraper.geo import GeoResolver
from proxyscraper.options import RunOptions
from proxyscraper.ui import CheckDashboard, LiveStats

DAY = 86400


def test_hits_cancelled_before_their_verdict_are_not_failures(tmp_path):
    async def go():
        confirming = asyncio.Event()

        class Checker:
            async def check(self, key):
                ptype, proxy = key.split(" ")
                return CheckResult(key, ptype, proxy, 100, "9.9.9.9")

            async def confirm(self, r):
                confirming.set()
                await asyncio.sleep(3600)  # still confirming when the run is stopped

        jobs = ["http 1.1.1.1:80"]
        stats = LiveStats({"http": 1})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 1, False)
        task = asyncio.ensure_future(pipeline.run_checks(
            jobs, Checker(), RunOptions(no_geo=True), dashboard, writer, GeoResolver(enabled=False),
            live_factory=lambda _: contextlib.nullcontext()))
        await confirming.wait()
        task.cancel()  # like --want being reached elsewhere, or Ctrl+C
        with contextlib.suppress(asyncio.CancelledError):
            return await task

    run = asyncio.run(go())
    assert run is None or "http 1.1.1.1:80" not in run.checked


def test_a_list_without_the_requested_types_is_still_reachable(tmp_path):
    st = srcs.SourceStats(tmp_path / "stats.json")
    for day in range(3):  # three runs with --types http on a list that only has socks5
        st.record_fetch("u", b"socks5://1.2.3.4:1080", 0, now=day * DAY, parsed=1)
    assert st.get("u").fail_streak == 0 and st.skip_reason("u", now=3 * DAY) is None
    st.record_fetch("v", b"<html>nothing</html>", 0, now=0, parsed=0)  # really no proxies at all
    assert st.get("v").fail_streak == 1


def test_outdated_lists_get_another_look_now_and_then(tmp_path):
    st = srcs.SourceStats(tmp_path / "stats.json")
    st.record_fetch("s", b"a", 1, now=1 * DAY)
    st.record_fetch("s", b"a", 1, now=10 * DAY)         # unchanged for 9 days
    assert st.skip_now("s", now=11 * DAY) == "outdated"
    assert st.skip_now("s", now=14 * DAY) is None        # three days later it is fetched again …
    assert st.skip_reason("s", now=14 * DAY) == "outdated"  # … while the status shown stays the same
    st.record_fetch("s", b"b", 1, now=14 * DAY)          # it changed: maintained again
    assert st.skip_reason("s", now=15 * DAY) is None


def test_without_the_cache_other_types_still_count_as_content(tmp_path, monkeypatch):
    from proxyscraper.fetchcache import FetchCache
    from proxyscraper.ui import CollectView

    async def fake_request(url, timeout=None, headers=None):
        return 200, {}, b"socks5://1.2.3.4:1080\n"

    monkeypatch.setattr(pipeline, "http_request", fake_request)
    url = "https://example.org/list.txt"
    st = srcs.SourceStats(tmp_path / "stats.json")
    asyncio.run(pipeline.scrape({url: "auto"}, ["http"], st, CollectView(1, 0.0), FetchCache(enabled=False)))
    assert st.get(url).fail_streak == 0  # it answered with socks5 proxies, --types http just doesn't want them
