"""Discovery runs daily and keeps what earlier runs found (#127)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from proxyscraper import sources as srcs

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def test_finds_add_up_and_old_ones_expire(tmp_path):
    path = tmp_path / "found.json"
    srcs.save_discovered({"https://a/http.txt": "http"}, path, now=NOW - timedelta(days=30))
    srcs.save_discovered({"https://b/socks5.txt": "socks5"}, path, now=NOW - timedelta(days=5))
    kept = srcs.save_discovered({"https://c/all.txt": "auto"}, path, now=NOW)
    assert kept == {"https://b/socks5.txt": "socks5", "https://c/all.txt": "auto"}  # a: not seen for 30 days
    assert srcs.load_discovered(path) == kept
    seen = json.loads(path.read_text())["last_seen"]
    assert seen["https://b/socks5.txt"] < seen["https://c/all.txt"]


def test_seeing_a_source_again_renews_it(tmp_path):
    path = tmp_path / "found.json"
    srcs.save_discovered({"https://a/http.txt": "http"}, path, now=NOW - timedelta(days=20))
    srcs.save_discovered({"https://a/http.txt": "http"}, path, now=NOW - timedelta(days=10))
    assert srcs.save_discovered({}, path, now=NOW) == {"https://a/http.txt": "http"}  # 10 days, not 20


def test_files_from_before_last_seen_count_from_their_date(tmp_path):
    path = tmp_path / "found.json"
    old = {"generated": (NOW - timedelta(days=2)).isoformat(), "sources": {"https://a/x.txt": "http"}}
    path.write_text(json.dumps(old))
    assert srcs.save_discovered({}, path, now=NOW) == {"https://a/x.txt": "http"}


def test_vpn_config_repos_and_test_corpora_are_skipped():
    assert srcs.classify_path("bench/corpus/scrape_http.txt") is None
    assert srcs.classify_path("subs/all.txt") is None and srcs.classify_path("subscriptions/all.txt") is None
    assert srcs.classify_path("proxies/socks5.txt") == "socks5"

    repos = [{"full_name": "someone/v2ray-config", "default_branch": "main", "stargazers_count": 9},
             {"full_name": "someone/free-vpn-nodes", "default_branch": "main", "stargazers_count": 8},
             {"full_name": "good/proxy-list", "default_branch": "main", "stargazers_count": 1}]
    tree = {"tree": [{"type": "blob", "path": "http.txt", "size": 5000}]}

    async def get(url, timeout=0, headers=None):
        return json.dumps({"items": repos} if "search/repositories" in url else tree).encode()

    found = asyncio.run(srcs.discover_github(get, token=None, max_repos=50))
    assert set(found) == {f"{srcs.GH_RAW}/good/proxy-list/main/http.txt"}


def test_a_rate_limit_waits_instead_of_giving_up(monkeypatch):
    monkeypatch.setattr(srcs, "RATE_LIMIT_WAIT", 0)
    calls = {"search": 0}

    async def get(url, timeout=0, headers=None):
        if "search/repositories" in url:
            calls["search"] += 1
            if calls["search"] == 2:
                raise ConnectionError("HTTP 403")  # what netio.http_get raises for the rate limit
            return json.dumps({"items": [{"full_name": f"o{calls['search']}/list", "default_branch": "main",
                                          "stargazers_count": 1}]}).encode()
        return json.dumps({"tree": [{"type": "blob", "path": "http.txt", "size": 5000}]}).encode()

    found = asyncio.run(srcs.discover_github(get, token=None, max_repos=500))
    # every query still ran: the one that hit the limit was repeated instead of ending the search
    assert calls["search"] == len(srcs.DISCOVERY_QUERIES) + 1
    assert len(found) == len(srcs.DISCOVERY_QUERIES)


def test_a_bad_token_doesnt_wait(monkeypatch):
    waited = []

    async def no_sleep(seconds):
        waited.append(seconds)

    monkeypatch.setattr(srcs.asyncio, "sleep", no_sleep)
    calls = {"search": 0}

    async def get(url, timeout=0, headers=None):
        calls["search"] += 1
        raise ConnectionError("HTTP 401")

    assert asyncio.run(srcs.discover_github(get, token="expired", max_repos=50)) == {}
    assert waited == []  # 401 won't get better by waiting a minute
    assert calls["search"] == len(srcs.DISCOVERY_QUERIES)  # one try per query, no retries


def test_old_finds_expire_even_when_no_search_runs(tmp_path):
    path = tmp_path / "found.json"
    srcs.save_discovered({"https://a/http.txt": "http"}, path, now=NOW - timedelta(days=30))
    srcs.save_discovered({"https://b/http.txt": "http"}, path, now=NOW - timedelta(days=1))
    assert srcs.load_discovered(path, now=NOW) == {"https://b/http.txt": "http"}


def test_vpn_repos_found_before_the_filter_are_dropped_on_load(tmp_path):
    path = tmp_path / "found.json"
    vpn = f"{srcs.GH_RAW}/someone/v2ray-config/main/all.txt"
    good = f"{srcs.GH_RAW}/someone/proxy-list/main/http.txt"
    path.write_text(json.dumps({"generated": NOW.isoformat(), "sources": {vpn: "auto", good: "http"}}))
    assert srcs.load_discovered(path, now=NOW) == {good: "http"}
