"""Lists found by discovery or in third-party meta lists are downloaded from public addresses only (SSRF)."""

import asyncio

from proxyscraper import pipeline
from proxyscraper import sources as srcs
from proxyscraper.fetchcache import FetchCache
from proxyscraper.netpolicy import BlockedTarget
from proxyscraper.options import RunOptions
from proxyscraper.ui import CollectView

CURATED = "https://example.com/curated.txt"
META = "https://meta.example/listed.txt"
FOUND = "https://found.example/proxies.txt"
OWN = "http://127.0.0.1:8000/mine.txt"


def plan_with_all_kinds(monkeypatch, tmp_path):
    monkeypatch.setattr(srcs, "load_source_file", lambda *a: ({CURATED: "http"}, ["https://meta.example/index"]))
    monkeypatch.setattr(srcs, "load_discovered", lambda *a, **k: {FOUND: "http", CURATED: "http"})
    monkeypatch.setattr(srcs, "discovered_age_days", lambda *a: 0.0)

    async def meta(urls, get):
        return {META: "http", CURATED: "http"}, 1
    monkeypatch.setattr(srcs, "resolve_meta", meta)
    opts = RunOptions(sources=[f"http={OWN}"], no_discover=True, all_sources=True)
    return asyncio.run(pipeline.collect_sources(opts, srcs.SourceStats(tmp_path / "stats.json")))


def test_found_and_meta_listed_sources_are_untrusted_curated_and_own_are_not(monkeypatch, tmp_path):
    plan = plan_with_all_kinds(monkeypatch, tmp_path)
    assert set(plan.sources) == {CURATED, META, FOUND, OWN}
    assert plan.untrusted == {META, FOUND}


def test_untrusted_sources_are_downloaded_with_the_public_only_policy(monkeypatch, tmp_path):
    seen = {}

    async def fake_request(url, timeout=None, headers=None, policy=None):
        seen[url] = policy
        if policy is not None and url == FOUND:
            raise BlockedTarget("non-public address")  # e.g. a name that resolves to 127.0.0.1 by now
        return 200, {}, b"45.67.89.10:8080\n"

    monkeypatch.setattr(pipeline, "http_request", fake_request)
    st = srcs.SourceStats(tmp_path / "stats.json")
    res = asyncio.run(pipeline.scrape({CURATED: "http", FOUND: "http", OWN: "http"}, ["http"], st,
                                      CollectView(3, 0.0), FetchCache(enabled=False), untrusted={FOUND}))
    assert seen[CURATED] is None and seen[OWN] is None  # chosen by us or by the user: unrestricted
    assert seen[FOUND] is pipeline.UNTRUSTED_SOURCE_POLICY
    assert pipeline.UNTRUSTED_SOURCE_POLICY.ports is None  # third-party lists on other ports keep working
    assert res.ok_sources == 2  # the blocked one simply failed
