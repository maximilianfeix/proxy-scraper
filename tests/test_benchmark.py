"""The comparison of the popular GitHub proxy lists: which ones are shown, in which order, and how."""

import json
from datetime import datetime, timezone

from proxyscraper import benchmark, publish, sourcepages

from .test_publish import run_dir
from .test_source_pages import RAW, record, stats

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def entry(name, checked, working, listed=None, status="active", last_change="2026-10-10T11:30:00+00:00"):
    return {"name": name, "url": f"https://github.com/{name}", "lists": 1, "listed": listed or checked,
            "checked": checked, "working": working, "share": round(100 * working / checked, 1) if checked else 0.0,
            "status": status, "last_change": last_change}


def test_only_the_popular_lists_highest_share_first():
    ranking = [entry("someone/else", 5000, 4000), entry("proxifly/free-proxy-list", 20000, 400),
               entry("monosans/proxy-list", 2000, 120), entry("TheSpeedX/PROXY-List", 8000, 160),
               entry("maximilianfeix/proxy-scraper", 900, 800)]
    picked = benchmark.select(ranking)
    assert [(s["rank"], s["name"]) for s in picked] == [
        (1, "monosans/proxy-list"), (2, "proxifly/free-proxy-list"), (3, "TheSpeedX/PROXY-List")]


def test_names_match_whatever_their_case_and_ties_go_to_more_working_proxies():
    picked = benchmark.select([entry("thespeedx/proxy-list", 1000, 20), entry("JETKAI/proxy-list", 5000, 100)])
    assert [s["name"] for s in picked] == ["JETKAI/proxy-list", "thespeedx/proxy-list"]


def test_too_few_checked_lists_are_shown_last_without_a_place():
    picked = benchmark.select([entry("clarketm/proxy-list", 100, 90), entry("mmpx12/proxy-list", 1000, 10),
                               entry("hookzof/socks5_list", 0, 0)])
    assert [(s["rank"], s["name"]) for s in picked] == [(1, "mmpx12/proxy-list"), (None, "clarketm/proxy-list")]
    page = benchmark.page(picked, NOW)
    assert 'title="too few checked to compare">–</span>' in page
    # a 90 % from 100 checks is no headline
    assert "mmpx12/proxy-list had the highest share" in page
    assert "clarketm" not in benchmark.chart_svg(picked, NOW)


def test_ago_reads_like_a_person_says_it():
    assert benchmark.ago("2026-10-10T11:30:00+00:00", NOW) == "within the hour"
    assert benchmark.ago("2026-10-10T07:00:00+00:00", NOW) == "5 h ago"
    assert benchmark.ago("2026-10-06T12:00:00+00:00", NOW) == "4 days ago"
    assert benchmark.ago("2026-09-07T12:00:00+00:00", NOW) == "7 Sep 2026"
    assert benchmark.ago(None, NOW) == benchmark.ago("not a date", NOW) == "–"


def test_page_json_and_charts(tmp_path):
    ranking = [entry("monosans/proxy-list", 2000, 120), entry("jetkai/proxy-list", 10000, 50, listed=14000,
                                                              status="outdated", last_change=None)]
    out = tmp_path / "public"
    assert benchmark.write_benchmark(ranking, out, NOW) == ["benchmark/"]
    page = (out / "benchmark" / "index.html").read_text(encoding="utf-8")
    assert "<h1>Which free proxy list on GitHub actually works?</h1>" in page
    assert '<link rel="canonical" href="https://proxy-scraper.de/benchmark/">' in page
    assert "monosans/proxy-list had the highest share" in page and "6.0 %" in page
    assert "14,000" in page and "unchanged for a week" in page
    assert page.index("monosans/proxy-list</a>") < page.index("jetkai/proxy-list</a>")
    # the method in plain words, and why our own list isn't in it
    assert "same exit IP" in page and "not a judgment of the maintainers" in page
    assert "own published list is not in the table" in page
    assert "honeypot" not in page.lower()
    data = json.loads((out / "benchmark.json").read_text(encoding="utf-8"))
    assert data["updated"] == "2026-10-10T12:00:00+00:00"
    assert [(s["rank"], s["name"], s["share"]) for s in data["lists"]] == [
        (1, "monosans/proxy-list", 6.0), (2, "jetkai/proxy-list", 0.5)]
    assert "proxifly/free-proxy-list" in data["not_measured"] and "jetkai/proxy-list" not in data["not_measured"]
    for theme in ("light", "dark"):
        svg = (out / f"benchmark-{theme}.svg").read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "monosans/proxy-list" in svg and "6.0 %" in svg and "<script" not in svg


def test_names_are_escaped_everywhere(tmp_path):
    ranking = [entry("monosans/proxy-list", 1000, 50)]
    evil = entry("proxifly/free-proxy-list", 1000, 10)
    evil["url"] = 'https://github.com/x"><script>'
    lists = benchmark.select([*ranking, evil])
    lists[1]["name"] = "<b>&evil</b>"
    page = benchmark.page(lists, NOW)
    assert "<b>&evil" not in page and "&lt;b&gt;&amp;evil&lt;/b&gt;" in page
    assert '"><script>' not in page
    svg = benchmark.chart_svg(lists, NOW)
    assert "<b>" not in svg and "&lt;b&gt;&amp;evil" in svg


def test_nothing_popular_nothing_written(tmp_path):
    out = tmp_path / "public"
    assert benchmark.write_benchmark([entry("someone/else", 1000, 10)], out, NOW) == []
    assert not (out / "benchmark").exists() and not (out / "benchmark.json").exists()


def test_page_without_any_ranked_list_says_so():
    page = benchmark.page(benchmark.select([entry("clarketm/proxy-list", 50, 5)]), NOW)
    assert "Too few of their proxies have been checked yet" in page
    assert "Not enough checks yet" in benchmark.chart_svg([], NOW)


def test_source_pages_write_it_link_it_and_publish_lists_it_in_the_sitemap(tmp_path):
    quality = stats(tmp_path, {f"{RAW}/monosans/proxy-list/main/http.txt": record(1000, 60),
                               f"{RAW}/a/lists/main/http.txt": record(1000, 20)})
    out = tmp_path / "public"
    assert sourcepages.write_source_pages(quality, out, NOW) == ["sources/", "benchmark/"]
    assert 'href="../benchmark/"' in (out / "sources" / "index.html").read_text(encoding="utf-8")
    quality.save()
    out = tmp_path / "published"
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=NOW, sources=quality.path) == 0
    assert "<loc>https://proxy-scraper.de/benchmark/</loc>" in (out / "sitemap.xml").read_text()
    assert (out / "benchmark-dark.svg").exists() and (out / "benchmark.json").exists()
    assert "https://proxy-scraper.de/benchmark/" in (out / "README.md").read_text(encoding="utf-8")
