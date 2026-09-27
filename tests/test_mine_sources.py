"""Discovery also reads the source lists of other proxy scrapers – and keeps only URLs that really hold proxies."""

import asyncio
import json

from proxyscraper import sources as srcs

LIST = "\n".join(f"8.8.{i // 250}.{i % 250 + 1}:8080" for i in range(30)).encode()
CONFIG = json.dumps({"sources": [
    "https://raw.githubusercontent.com/someone/lists/main/socks5.txt",      # a real list -> kept, socks5
    "https://example.org/api/proxies?format=text",                         # a real list, type unknown -> auto
    "https://www.some-proxy-site.com/free-proxy-list/",                    # an HTML page -> dropped
    "https://example.org/api/{protocol}.txt",                               # a template -> never fetched
    "https://raw.githubusercontent.com/someone/v2ray-configs/main/all.txt",  # VPN configs -> never fetched
    "https://known.example/http.txt",                                       # already a source -> not fetched again
]}).encode()


def fake_get(fetched):
    async def get(url, timeout=0, headers=None):
        fetched.append(url)
        if "search/repositories" in url:
            return json.dumps({"items": [{"full_name": "dev/scraper", "default_branch": "main",
                                          "stargazers_count": 5}]}).encode()
        if "/git/trees/" in url:
            return json.dumps({"tree": [
                {"type": "blob", "path": "config/sources.json", "size": 800},
                {"type": "blob", "path": "main.py", "size": 800},
            ]}).encode()
        if url.endswith("config/sources.json"):
            return CONFIG
        if "some-proxy-site" in url:
            return b"<html><body>no proxies in plain text here</body></html>"
        return LIST
    return get


def test_urls_from_scraper_configs_are_checked_before_they_count():
    fetched = []
    found = asyncio.run(srcs.discover_github(fake_get(fetched), token=None, max_repos=10,
                                             known={"https://known.example/http.txt"}))
    assert found == {
        "https://raw.githubusercontent.com/someone/lists/main/socks5.txt": "socks5",
        "https://example.org/api/proxies?format=text": "auto",   # plain ip:port lines: auto reads them as http
    }
    assert not any("{protocol}" in u or "v2ray" in u or "known.example" in u for u in fetched)
    # only files that look like source lists are read
    assert "https://raw.githubusercontent.com/dev/scraper/main/main.py" not in fetched


def test_mined_urls_are_capped():
    many = json.dumps([f"https://example.org/list{i}.txt" for i in range(srcs.MAX_MINED_CHECKS + 50)]).encode()
    fetched = []
    base = fake_get(fetched)

    async def get(url, timeout=0, headers=None):
        if url.endswith("config/sources.json"):
            fetched.append(url)
            return many
        return await base(url, timeout, headers)

    found = asyncio.run(srcs.discover_github(get, token=None, max_repos=10))
    assert len(found) == srcs.MAX_MINED_CHECKS


def test_the_type_can_sit_in_the_query_string():
    assert srcs._mined_type("https://api.example.com/v2/?request=get&protocol=socks4") == "socks4"


def test_scheme_lists_stay_auto():
    data = "\n".join(f"socks5://8.8.{i // 250}.{i % 250 + 1}:1080" for i in range(30)).encode()
    assert srcs._readable_type("https://example.org/mixed", data) == "auto"
    assert srcs._readable_type("https://example.org/mixed", b"nothing") is None


def test_urls_to_local_or_private_hosts_are_never_fetched():
    config = json.dumps(["http://127.0.0.1/proxy.txt", "http://localhost/proxies.txt",
                         "http://169.254.169.254/latest/proxy", "http://10.0.0.5/socks5.txt",
                         "http://printer.local/proxy.txt", "https://example.org:8443/proxy.txt",
                         "https://example.org/proxy.txt"]).encode()
    assert srcs.mined_urls(config) == ["https://example.org/proxy.txt"]


def test_repo_meta_files_dont_take_the_config_slots():
    assert not srcs._CONFIG_PATH_RE.search(".github/ISSUE_TEMPLATE/config.yml")
    assert not srcs._CONFIG_PATH_RE.search(".vscode/settings.json")
    assert srcs._CONFIG_PATH_RE.search("src/sources.py")


def test_slow_hosts_cant_stall_discovery(monkeypatch):
    monkeypatch.setattr(srcs, "MINE_DEADLINE", 0.2)
    config = json.dumps([f"https://slow{i}.example/proxy.txt" for i in range(5)]
                        + ["https://fast.example/proxy.txt"]).encode()

    async def get(url, timeout=0, headers=None):
        if "slow" in url:
            await asyncio.sleep(30)
        return config if url == "cfg" else LIST

    async def go():
        return await asyncio.wait_for(srcs._mine(get, ["cfg"], set()), 5)
    assert asyncio.run(go()) == {"https://fast.example/proxy.txt": "auto"}


def test_the_minimum_counts_addresses_not_typed_keys():
    # untyped lists turn every address into an http and a socks5 key: 10 addresses are still 10
    ten = "\n".join(f"8.8.8.{i}:8080" for i in range(1, 11)).encode()
    assert srcs._readable_type("https://example.org/proxies.txt", ten) is None
    twenty = "\n".join(f"8.8.8.{i}:8080" for i in range(1, 21)).encode()
    assert srcs._readable_type("https://example.org/proxies.txt", twenty) == "auto"
