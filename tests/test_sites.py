"""Which big sites let a proxy through: the verdict per site, and the step that fills it into a run."""

import asyncio
import json

import pytest

from proxyscraper import sites

GOOGLE, REDDIT, AMAZON = (sites.SITE[n] for n in ("google", "reddit", "amazon"))


@pytest.mark.parametrize("site,status,location,expected", [
    (GOOGLE, 200, "", True),
    (GOOGLE, 302, "https://www.google.com/sorry/index?continue=x", False),   # the captcha page
    (GOOGLE, 429, "", False),
    (GOOGLE, 302, "https://consent.google.com/ml?continue=x", True),        # EU consent screen: got through
    (GOOGLE, 502, "", None),                                                # says nothing about blocking
    (REDDIT, 200, "", True),
    (REDDIT, 403, "", False),
    (REDDIT, 429, "", False),
    (REDDIT, 301, "https://www.reddit.com/", None),
    (AMAZON, 200, "", True),
    (AMAZON, 202, "", False),                                               # the bot check
    (AMAZON, 503, "", False),
    (AMAZON, 0, "", None),
])
def test_verdicts(site, status, location, expected):
    assert site.verdict(status, location) is expected


def test_head_parsing():
    head = b"HTTP/1.1 302 Found\r\nContent-Type: text/html\r\nlocation: https://www.google.com/sorry/index\r\n\r\n"
    assert sites.parse_head(head) == (302, "https://www.google.com/sorry/index")
    assert sites.parse_head(b"garbage\r\n\r\n") == (0, "")


def run_dir(tmp_path, rows):
    d = tmp_path / "run"
    d.mkdir()
    (d / "proxies.json").write_text(json.dumps(rows))
    return d


def row(n, https=True):
    return {"url": f"socks5://1.1.1.{n}:1080", "ptype": "socks5", "proxy": f"1.1.1.{n}:1080", "https": https,
            "latency": 100}


def test_only_https_proxies_are_probed_and_only_clear_answers_are_kept(tmp_path):
    asked = []

    async def probe(r, site, ip):
        asked.append((r["proxy"], site.name))
        if r["proxy"].endswith(".2:1080"):
            return None                      # timed out: no verdict
        return site.name != "reddit"         # reddit blocks everyone here

    d = run_dir(tmp_path, [row(1), row(2), row(3, https=False)])
    stats = asyncio.run(sites.fill_run(d, probe=probe, resolve=lambda host: "10.0.0.1"))
    rows = {r["proxy"]: r for r in json.loads((d / "proxies.json").read_text())}
    assert rows["1.1.1.1:1080"]["sites"] == {"google": True, "reddit": False, "amazon": True}
    assert rows["1.1.1.2:1080"]["sites"] == {}
    assert "sites" not in rows["1.1.1.3:1080"] or rows["1.1.1.3:1080"]["sites"] == {}
    assert {p for p, _ in asked} == {"1.1.1.1:1080", "1.1.1.2:1080"}
    assert stats == {"google": 1, "reddit": 0, "amazon": 1}


def test_a_site_that_cant_be_resolved_is_skipped(tmp_path):
    async def probe(r, site, ip):
        return True

    def resolve(host):
        if "reddit" in host:
            raise OSError("no DNS")
        return "10.0.0.1"

    d = run_dir(tmp_path, [row(1)])
    asyncio.run(sites.fill_run(d, probe=probe, resolve=resolve))
    assert json.loads((d / "proxies.json").read_text())[0]["sites"] == {"google": True, "amazon": True}


# --------------------------------------------------------------------------- using the verdicts

def test_publish_writes_a_list_per_site_and_counts(tmp_path):
    from proxyscraper import publish
    from tests.test_publish import run_dir as publish_run
    d = publish_run(tmp_path)
    rows = json.loads((d / "proxies.json").read_text())
    for r in rows:
        r["sites"] = {"google": r["ptype"] == "socks5", "reddit": False} if r.get("https") else {}
    (d / "proxies.json").write_text(json.dumps(rows))
    out = tmp_path / "public"
    publish.publish(d, out, minimum=2)
    assert (out / "works-with" / "google.txt").read_text() == "socks5://2.2.2.2:1080\n"
    assert (out / "works-with" / "reddit.txt").read_text() == ""
    assert (out / "works-with" / "amazon.txt").read_text() == ""
    stats = json.loads((out / "stats.json").read_text())
    assert stats["sites"] == {"google": 1, "reddit": 0, "amazon": 0}
    import csv
    with (out / "proxies.csv").open(newline="", encoding="utf-8") as fh:
        by_url = {r["url"]: r for r in csv.DictReader(fh)}
    assert by_url["socks5://2.2.2.2:1080"]["works_with"] == "google"
    assert by_url["http://1.1.1.0:80"]["works_with"] == ""


def test_filters_for_agents_and_python():
    from proxyscraper import agent
    rows = [{"url": "http://1.1.1.1:80", "ptype": "http", "proxy": "1.1.1.1:80", "latency": 1,
             "sites": {"google": True, "reddit": False}},
            {"url": "http://2.2.2.2:80", "ptype": "http", "proxy": "2.2.2.2:80", "latency": 2, "sites": {}}]
    assert [r["url"] for r in agent.select(rows, works_on=["google"])] == ["http://1.1.1.1:80"]
    assert agent.select(rows, works_on=["google", "reddit"]) == []
    assert agent.describe(rows[0])["works_on"] == ["google"]
    with pytest.raises(agent.AgentError, match="google"):
        agent.select(rows, works_on=["bing"])
