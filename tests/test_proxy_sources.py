import asyncio
import json

import pytest

from proxyscraper import sources as srcs

DAY = srcs.DAY


def test_normalize_github_urls():
    assert (
        srcs.normalize_url("https://github.com/a/b/raw/refs/heads/main/http.txt,,ColonURL")
        == "https://raw.githubusercontent.com/a/b/main/http.txt"
    )
    assert (
        srcs.normalize_url("https://raw.githubusercontent.com/a/b/refs/heads/main/x.txt")
        == "https://raw.githubusercontent.com/a/b/main/x.txt"
    )
    assert srcs.normalize_url("https://x.org/{YYYY}/{MM}.txt") is None
    assert srcs.normalize_url("not a url") is None


def test_parse_url_list_skips_comments_and_dedupes():
    data = b"# comment\nhttps://x.org/a.txt\nhttps://x.org/a.txt\n\nhttps://x.org/b.txt,,SpaceURL\n"
    assert srcs.parse_url_list(data, "https") == {"https://x.org/a.txt": "http", "https://x.org/b.txt": "http"}


def test_parse_monosans_toml_sections():
    toml = b"""
[scraping]
enabled = true
[scraping.http]
urls = [
  "https://h.org/http.txt",
  # "https://h.org/disabled.txt",
]
[scraping.socks5]
urls = ["https://h.org/s5.txt"]
[output]
path = "https://not-a-source.org/x"
"""
    assert srcs.parse_monosans_toml(toml) == {"https://h.org/http.txt": "http", "https://h.org/s5.txt": "socks5"}


def test_classify_path():
    assert srcs.classify_path("proxies/protocols/socks5/data.txt") == "socks5"
    assert srcs.classify_path("https.txt") == "http"
    assert srcs.classify_path("all_proxies.txt") == "auto"
    assert srcs.classify_path("countries/DE/http.txt") is None
    assert srcs.classify_path("v2ray/vmess.txt") is None
    assert srcs.classify_path("us.txt") is None
    assert srcs.classify_path("http.json") is None
    assert srcs.classify_path("a/b/c/d/http.txt") is None


def test_resolve_meta_tolerates_failures():
    async def get(url, timeout=0, headers=None):
        if "bad" in url:
            raise ConnectionError
        return b"https://x.org/one.txt\n"

    meta = [{"url": "https://ok", "type": "socks4"}, {"url": "https://bad", "type": "http"}]
    found, ok = asyncio.run(srcs.resolve_meta(meta, get))
    assert (found, ok) == ({"https://x.org/one.txt": "socks4"}, 1)


def test_discover_github_filters_spam_owners_and_files():
    repos = [{"full_name": f"spam/r{i}", "default_branch": "main", "stargazers_count": 100 - i} for i in range(5)]
    repos.append({"full_name": "good/list", "default_branch": "main", "stargazers_count": 1})
    tree = {"tree": [
        {"type": "blob", "path": "http.txt", "size": 5000},
        {"type": "blob", "path": "README.md", "size": 5000},
        {"type": "blob", "path": "socks5.txt", "size": 10},  # zu klein
    ]}

    async def get(url, timeout=0, headers=None):
        if "search/repositories" in url:
            return json.dumps({"items": repos}).encode()
        return json.dumps(tree).encode()

    found = asyncio.run(srcs.discover_github(get, token=None, max_repos=50))
    owners = {u.split("/")[3] for u in found}
    assert owners == {"spam", "good"}
    assert sum(1 for u in found if "/spam/" in u) == srcs.MAX_REPOS_PER_OWNER
    assert all(u.endswith("/http.txt") and t == "http" for u, t in found.items())


def test_stats_skip_rules(tmp_path):
    st = srcs.SourceStats(tmp_path / "s.json")
    now = 1_000_000.0

    # unerreichbar nach 3 Fehlschlägen, nach der Pause wieder erlaubt
    for _ in range(3):
        st.record_fetch("u", None, 0, now=now)
    assert st.skip_reason("u", now=now + 1) == "unerreichbar"
    assert st.skip_reason("u", now=now + srcs.UNREACHABLE_PAUSE + 1) is None

    # veraltet: Inhalt über eine Woche unverändert
    st.record_fetch("s", b"same", 10, now=now)
    st.record_fetch("s", b"same", 10, now=now + 8 * DAY)
    assert st.skip_reason("s", now=now + 8 * DAY) == "veraltet"
    st.record_fetch("s", b"new", 10, now=now + 9 * DAY)
    assert st.skip_reason("s", now=now + 9 * DAY) is None

    # tot: zwei Läufe, genug Prüfungen, kein Treffer
    st.record_checks({"d": (400, 0)})
    assert st.skip_reason("d") is None  # ein Lauf reicht nicht
    st.record_checks({"d": (400, 0)})
    assert st.skip_reason("d") == "tot"


def test_stats_score_and_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    st = srcs.SourceStats(path)
    st.record_checks({"good": (100, 40), "bad": (100, 1)})
    assert st.score("good") > st.score("bad") > 0
    assert 0 < st.score("unknown") < 0.05
    st.save()
    again = srcs.SourceStats(path)
    assert again.score("good") == st.score("good")


def test_stats_corrupt_file_starts_fresh(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{kaputt")
    with pytest.warns(UserWarning, match="unlesbar"):
        assert srcs.SourceStats(path).records == {}


def test_curated_sources_file_is_valid():
    sources, meta = srcs.load_source_file()
    assert len(sources) > 100
    assert set(sources.values()) <= set(srcs.SOURCE_TYPES)
    assert meta and all("url" in m for m in meta)
