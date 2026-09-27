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
        "https://example.org/api/proxies?format=text": "auto",
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
