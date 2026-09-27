"""The weekly report: what a week of hourly checks says about free proxies, as a page, markdown and a post."""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from proxyscraper import report

NOW = datetime(2026, 9, 27, 12, 17, tzinfo=timezone.utc)


def runs(n, total=1000):
    return [{"updated": (NOW - timedelta(hours=n - 1 - i)).isoformat(), "total": total + i,
             "by_type": {"http": 500, "socks4": 100, "socks5": 400 + i}, "median_latency": 1500 - i}
            for i in range(n)]


def row(n, hosting, google, reddit=None, **extra):
    sites = {"google": google}
    if reddit is not None:
        sites["reddit"] = reddit
    return {"url": f"http://1.1.{n // 250}.{n % 250}:80", "proxy": f"1.1.{n // 250}.{n % 250}:80", "ptype": "http",
            "latency": 500, "https": True, "anonymity": "elite", "country": "US" if n % 2 else "DE",
            "hosting": hosting, "sites": sites, **extra}


def seen(counts):
    """{runs listed: how many proxies} -> url -> bits"""
    out, n = {}, 0
    for listed, many in counts.items():
        for _ in range(many):
            # listed in the runs before this one (all 48 of them: this one too)
            out[f"http://9.9.{n // 250}.{n % 250}:80"] = ((1 << listed) - 1) << (listed < 48)
            n += 1
    return out


def facts(**kw):
    rows = [row(i, hosting=i < 10, google=i >= 5) for i in range(20)]
    base = {"rows": rows, "runs": runs(48), "seen": seen({1: 60, 2: 20, 24: 15, 48: 5}), "now": NOW}
    base.update(kw)
    return report.weekly_facts(**base)


def test_lifetimes_come_from_the_timelines():
    f = facts()
    assert f["distinct"] == 100
    # the 5 listed in all 48 runs are still there: their lifetime isn't over, so it isn't counted
    assert f["ended"] == 95 and f["gone_after_one_run"] == 60 and f["lasted_a_day"] == 15
    assert f["lasted_whole_window"] == 5


def test_a_lifetime_is_checks_in_a_row_and_must_start_inside_the_window():
    s = {"http://1.1.1.1:80": 0b1010,                   # two single checks, 2 runs apart: the last one counts, 1
         "http://2.2.2.2:80": ((1 << 47) - 1) << 1,     # from the oldest run of the window: started before, unknown
         "http://3.3.3.3:80": 0b111100}                 # 4 in a row, ended 2 runs ago
    f = facts(seen=s)
    assert f["ended"] == 2 and f["gone_after_one_run"] == 1
    assert dict(f["lifetimes"])["2–5 checks"] == 1


def test_runs_and_totals_of_the_window():
    f = facts()
    assert f["runs"] == 48 and f["peak"] == 1047 and f["low"] == 1000
    assert f["since"] == NOW - timedelta(hours=47)  # history younger than a week: the report says so


def test_datacenter_vs_the_rest_per_site():
    f = facts()
    google = f["sites"]["google"]
    # rows 0-9 datacenter, rows 5-19 got through: datacenter 5/10, others 10/10
    assert google == {"through": 15, "answered": 20, "datacenter": 50, "other": 100}


def test_markdown_page_and_post(tmp_path):
    report.write_report(facts(), tmp_path)
    md = (tmp_path / "report" / "report.md").read_text(encoding="utf-8")
    assert "63 %" in md and "100 different proxies" in md and "Google" in md
    html = (tmp_path / "report" / "index.html").read_text(encoding="utf-8")
    assert "<h1>" in html and "63 %" in html
    post = (tmp_path / "report" / "post.txt").read_text(encoding="utf-8").strip()
    assert len(post) <= 280 and "maximilianfeix.github.io/proxy-scraper/report/" in post
    for theme in ("dark", "light"):
        ET.fromstring((tmp_path / "report" / f"lifetimes-{theme}.svg").read_text(encoding="utf-8"))


def test_a_fresh_list_still_gets_a_report(tmp_path):
    f = report.weekly_facts(rows=[row(1, False, True)], runs=runs(1), seen={}, now=NOW)
    report.write_report(f, tmp_path)
    assert (tmp_path / "report" / "index.html").exists()


def test_proxies_new_in_this_run_are_not_counted_as_gone():
    s = seen({1: 60, 24: 40})
    s.update({f"http://8.8.8.{i}:80": 0b1 for i in range(1, 51)})  # first seen right now: not gone, not counted
    s.update({f"http://7.7.7.{i}:80": 0b10 for i in range(1, 11)})  # one check, an hour ago: gone
    f = facts(seen=s)
    assert f["distinct"] == 160 and f["ended"] == 110 and f["gone_after_one_run"] == 70


def test_no_made_up_comparisons():
    rows = [row(i, hosting=None, google=True) for i in range(5)]  # no provider data at all
    f = report.weekly_facts(rows=rows, runs=runs(3), seen={}, now=NOW)
    assert f["datacenter"] is None and f["sites"]["google"]["datacenter"] is None
    md = report.markdown(f)
    assert "datacenter" not in md


def test_long_runners_that_are_still_listed_are_named():
    s = {"http://1.1.1.1:80": 0b10, "http://2.2.2.2:80": (1 << 30) - 1}  # one gone after a check, one up 30 in a row
    f = facts(seen=s)
    assert f["lasted_a_day"] == 0 and f["up_a_day_now"] == 1
    md = report.markdown(f)
    assert "None of them lasted 24 checks in a row" in md and "1 proxy on the list right now has" in md


def test_tiny_shares_dont_read_as_zero():
    assert report._share(3, 11_122) == "under 0.1 %"
    assert report._share(30, 11_122) == "0.3 %"
    assert report._share(0, 10) == "0 %"


def test_an_atom_feed_with_one_entry_per_week(tmp_path):
    report.write_report(facts(), tmp_path)
    feed = ET.fromstring((tmp_path / "report" / "feed.xml").read_text(encoding="utf-8"))
    atom = "{http://www.w3.org/2005/Atom}"
    entries = feed.findall(f"{atom}entry")
    assert len(entries) == 1
    week = NOW.isocalendar()
    assert entries[0].find(f"{atom}id").text.endswith(f"{week[0]}-W{week[1]:02d}")  # same id all week long
    assert "63 %" in entries[0].find(f"{atom}content").text
    assert feed.find(f"{atom}link[@rel='self']").get("href").endswith("/report/feed.xml")
    page = (tmp_path / "report" / "index.html").read_text(encoding="utf-8")
    assert 'type="application/atom+xml"' in page
