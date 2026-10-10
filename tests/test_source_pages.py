"""The public ranking of the sources: which lists deliver proxies that pass the checks."""

import json
from datetime import datetime, timezone

from proxyscraper import publish, sourcepages
from proxyscraper.sources import DAY, SourceRecord, SourceStats

from .test_publish import run_dir

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
RAW = "https://raw.githubusercontent.com"


def stats(tmp_path, records):
    quality = SourceStats(tmp_path / "source_stats.json")
    quality.records = records
    return quality


def record(checked, working, runs=1, count=0, changed_days_ago=0.0, **more):
    then = NOW.timestamp() - changed_days_ago * DAY
    return SourceRecord(first_seen=NOW.timestamp() - 30 * DAY, last_fetch=NOW.timestamp(), count=count or checked,
                        last_change=then, checked=checked, working=working, runs=runs, **more)


def test_publisher_names_a_github_repo_and_anything_else_by_host():
    assert sourcepages.publisher(f"{RAW}/TheSpeedX/PROXY-List/master/http.txt") == (
        "TheSpeedX/PROXY-List", "https://github.com/TheSpeedX/PROXY-List")
    assert sourcepages.publisher("https://www.proxy-list.download/api/v1/get?type=http") == (
        "proxy-list.download", "https://www.proxy-list.download/")
    assert sourcepages.publisher("https://api.proxyscrape.com/v2/?request=get") == (
        "api.proxyscrape.com", "https://api.proxyscrape.com/")


def test_files_of_one_repo_count_as_one_source(tmp_path):
    quality = stats(tmp_path, {
        f"{RAW}/a/lists/main/http.txt": record(1000, 20, count=5000),
        f"{RAW}/a/lists/main/socks5.txt": record(1000, 60, count=3000),
        f"{RAW}/b/proxies/main/all.txt": record(400, 4),
    })
    ranking = sourcepages.rank(quality, NOW)
    assert [(s["name"], s["lists"], s["listed"], s["checked"], s["working"], s["share"]) for s in ranking] == [
        ("a/lists", 2, 8000, 2000, 80, 4.0), ("b/proxies", 1, 400, 400, 4, 1.0)]
    assert ranking[0]["url"] == "https://github.com/a/lists"


def test_numbers_are_per_run_not_the_decaying_sums(tmp_path):
    # three runs of 1000 checks and 50 hits each leave 1750 and 87.5 in the statistics
    quality = stats(tmp_path, {f"{RAW}/a/lists/main/http.txt": record(1750, 87.5, runs=3)})
    (source,) = sourcepages.rank(quality, NOW)
    assert (source["checked"], source["working"], source["share"]) == (1000, 50, 5.0)


def test_a_source_that_was_never_checked_or_is_our_own_list_stays_out(tmp_path):
    quality = stats(tmp_path, {
        f"{RAW}/a/lists/main/http.txt": record(500, 5),
        f"{RAW}/new/one/main/http.txt": SourceRecord(first_seen=NOW.timestamp(), count=10),
        f"{RAW}/maximilianfeix/proxy-scraper/proxy-list/all.txt": record(900, 800),
        f"{RAW}/maximilianfeix/free-proxy-list/main/all.txt": record(900, 800),
    })
    assert [s["name"] for s in sourcepages.rank(quality, NOW)] == ["a/lists"]


def test_status_says_when_a_list_is_no_longer_maintained_or_dead(tmp_path):
    quality = stats(tmp_path, {
        f"{RAW}/fresh/x/main/a.txt": record(500, 10),
        f"{RAW}/old/x/main/a.txt": record(500, 10, changed_days_ago=20),
        f"{RAW}/dead/x/main/a.txt": record(900, 0, runs=3),
        f"{RAW}/half/x/main/a.txt": record(500, 10),
        f"{RAW}/half/x/main/b.txt": record(500, 10, changed_days_ago=20),
        f"{RAW}/mixed/x/main/a.txt": record(900, 0, runs=3),
        f"{RAW}/mixed/x/main/b.txt": record(900, 0, runs=3),
        f"{RAW}/mixed/x/main/c.txt": record(500, 10, changed_days_ago=20),
    })
    status = {s["name"]: s["status"] for s in sourcepages.rank(quality, NOW)}
    # the best file decides: a source is only dead when every one of its files is
    assert status == {"fresh/x": "active", "old/x": "outdated", "dead/x": "dead", "half/x": "active",
                      "mixed/x": "outdated"}


def test_page_and_json(tmp_path):
    quality = stats(tmp_path, {
        f"{RAW}/a/lists/main/http.txt": record(1000, 20),
        f"{RAW}/b/<script>/main/all.txt": record(400, 40),
        f"{RAW}/tiny/x/main/all.txt": record(10, 9),
    })
    out = tmp_path / "public"
    assert sourcepages.write_source_pages(quality, out, NOW) == ["sources/"]
    page = (out / "sources" / "index.html").read_text(encoding="utf-8")
    assert "<h1>Which free proxy lists actually work?</h1>" in page
    assert 'href="https://github.com/a/lists"' in page and "2.0 %" in page
    assert "<script>/" not in page and "b/&lt;script&gt;" in page
    assert '<link rel="canonical" href="https://maximilianfeix.github.io/proxy-scraper/sources/">' in page
    # ten checks say too little for the table of the best shares, however good they look
    best = page.split("Highest share", 1)[1].split("</table>", 1)[0]
    assert "b/&lt;script&gt;" in best and "tiny/x" not in best
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    assert data["updated"] == "2026-10-10T12:00:00+00:00"
    assert [s["name"] for s in data["sources"]] == ["b/<script>", "a/lists", "tiny/x"]
    assert set(data["sources"][0]) == {"name", "url", "lists", "listed", "checked", "working", "share", "status",
                                       "last_change"}


def test_no_statistics_no_page(tmp_path):
    out = tmp_path / "public"
    assert sourcepages.write_source_pages(stats(tmp_path, {}), out, NOW) == []
    assert not (out / "sources").exists()


def test_publish_adds_the_ranking_to_the_site_and_the_sitemap(tmp_path):
    quality = stats(tmp_path, {f"{RAW}/a/lists/main/http.txt": record(1000, 20)})
    quality.save()
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=NOW, sources=quality.path) == 0
    assert (out / "sources" / "index.html").exists() and (out / "sources.json").exists()
    assert "<loc>https://maximilianfeix.github.io/proxy-scraper/sources/</loc>" in (out / "sitemap.xml").read_text()
    assert 'href="sources/"' in (out / "index.html").read_text(encoding="utf-8")


def test_publish_works_without_the_statistics(tmp_path):
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=NOW, sources=tmp_path / "missing.json") == 0
    assert not (out / "sources").exists()
    assert "/sources/</loc>" not in (out / "sitemap.xml").read_text()
