import json
from datetime import datetime, timezone

from proxyscraper import publish
from proxyscraper.checker import CheckResult
from proxyscraper.output import ResultWriter


def run_dir(tmp_path, n=3):
    rows = [
        CheckResult(f"http 1.1.1.{i}:80", "http", f"1.1.1.{i}:80", 100 * (i + 1), "9.9.9.9", i % 2 == 0,
                    "elite" if i == 0 else "anonymous", "DE")
        for i in range(n)
    ]
    rows.append(CheckResult("socks5 2.2.2.2:1080", "socks5", "2.2.2.2:1080", 50, "8.8.8.8", True, "elite", "US"))
    w = ResultWriter(run_dir=tmp_path / "run")
    w.finalize(rows)
    return tmp_path / "run"


def test_publish_writes_lists_badges_and_readme(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    out = tmp_path / "public"
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=now) == 0

    def read(name):
        return (out / name).read_text(encoding="utf-8")

    assert read("all.txt").splitlines()[0] == "socks5://2.2.2.2:1080"  # schnellster zuerst
    assert read("http.txt").splitlines() == ["1.1.1.0:80", "1.1.1.1:80", "1.1.1.2:80"]
    assert read("socks5.txt") == "2.2.2.2:1080\n"
    assert read("socks4.txt") == ""
    assert len(read("https.txt").splitlines()) == 3
    assert len(read("elite.txt").splitlines()) == 2

    total = json.loads(read("badges/total.json"))
    assert total == {"schemaVersion": 1, "label": "working proxies", "message": "4", "color": "brightgreen"}
    updated = json.loads(read("badges/updated.json"))
    assert updated == {"schemaVersion": 1, "label": "updated", "message": "2026-09-24 18:00 UTC", "color": "grey"}
    stats = json.loads(read("stats.json"))
    assert stats["by_type"] == {"http": 3, "socks4": 0, "socks5": 1}
    assert stats["countries"] == {"DE": 3, "US": 1}

    readme = read("README.md")
    assert "2026-09-24 18:00 UTC" in readme and "latency, country, HTTPS, anonymity" in readme
    assert "raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt" in readme
    assert "**4** working proxies" in summary.read_text(encoding="utf-8")


def test_publish_skips_when_too_few(tmp_path):
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path, n=0), out, minimum=20) == publish.SKIP_EXIT_CODE
    assert not out.exists()


def test_median_latency_for_even_count():
    rows = [{"latency": ms, "ptype": "http"} for ms in (100, 200, 300, 400)]
    assert publish.stats_for(rows, datetime.now(timezone.utc))["median_latency"] == 250


def test_num():
    assert publish.num(1234567) == "1,234,567"


def test_proxies_with_credentials_are_never_published(tmp_path):
    rows = [CheckResult(f"http 1.1.1.{i}:80", "http", f"1.1.1.{i}:80", 100, "9.9.9.9", True, "elite", "DE")
            for i in range(3)]
    rows.append(CheckResult("socks5 alice:geheim@2.2.2.2:1080", "socks5", "alice:geheim@2.2.2.2:1080", 50,
                            "8.8.8.8", True, "elite", "US"))
    ResultWriter(run_dir=tmp_path / "run").finalize(rows)
    out = tmp_path / "public"
    assert publish.publish(tmp_path / "run", out, minimum=2) == 0
    everything = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*")
                         if p.is_file() and p.suffix not in (".png", ".woff2"))
    assert "geheim" not in everything and "alice" not in everything and "2.2.2.2" not in everything
    assert (out / "http.txt").read_text().count("\n") == 3


def test_publish_writes_the_website_and_extends_the_history(tmp_path):
    previous = tmp_path / "history.json"
    previous.write_text(json.dumps([{"updated": f"2026-09-{d:02d}T00:00:00+00:00", "total": d, "https": 1,
                                     "by_type": {}, "median_latency": 1} for d in range(1, 4)]))
    out = tmp_path / "public"
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=now, history=previous) == 0
    assert (out / "index.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    for image in ("og.png", "logo.png", "apple-touch-icon.png"):  # link previews and the touch icon
        assert (out / image).read_bytes().startswith(b"\x89PNG")
    assert (out / ".nojekyll").exists()
    runs = json.loads((out / "history.json").read_text())
    assert [r["total"] for r in runs] == [1, 2, 3, 4] and runs[-1]["updated"] == "2026-09-24T18:00:00+00:00"


def test_history_is_capped_and_survives_garbage(tmp_path):
    previous = tmp_path / "history.json"
    previous.write_text(json.dumps([{"total": i} for i in range(publish.HISTORY_LIMIT + 50)] + ["kaputt", {"x": 1}]))
    out = tmp_path / "public"
    publish.publish(run_dir(tmp_path), out, minimum=2, history=previous)
    runs = json.loads((out / "history.json").read_text())
    assert len(runs) == publish.HISTORY_LIMIT and runs[-1]["total"] == 4
    previous.write_text("{not json")
    publish.publish(run_dir(tmp_path), tmp_path / "public2", minimum=2, history=previous)
    assert len(json.loads((tmp_path / "public2" / "history.json").read_text())) == 1


def test_website_ships_with_the_package():
    from proxyscraper.publish import SITE
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert "proxies.json" in html and "history.json" in html and "<script" in html
    for image in ("og.png", "logo.png", "apple-touch-icon.png"):  # package-data must include the images too
        assert (SITE / image).is_file()
    assert 'property="og:image"' in html and "apple-touch-icon.png" in html


def test_stats_count_datacenter_exits(tmp_path):
    rows = [CheckResult(f"http 1.1.1.{i}:80", "http", f"1.1.1.{i}:80", 100, "9.9.9.9", True, "elite", "DE")
            for i in range(4)]
    ResultWriter(run_dir=tmp_path / "run").finalize(rows)
    publish.publish(tmp_path / "run", tmp_path / "noprov", minimum=2)
    assert json.loads((tmp_path / "noprov" / "stats.json").read_text())["datacenter"] is None  # no data
    for r in rows:
        r.org = "Some ISP"
    rows[0].hosting, rows[0].org = True, "Hetzner Online GmbH"
    ResultWriter(run_dir=tmp_path / "run").finalize(rows)
    publish.publish(tmp_path / "run", tmp_path / "public", minimum=2)
    assert json.loads((tmp_path / "public" / "stats.json").read_text())["datacenter"] == 1


def test_streaks_count_consecutive_runs(tmp_path):
    previous = tmp_path / "streaks.json"
    stable = publish.STABLE_RUNS
    previous.write_text(json.dumps({"socks5://2.2.2.2:1080": stable, "http://1.1.1.0:80": 1, "http://7.7.7.7:80": 9,
                                    "kaputt": "x"}))
    out = tmp_path / "public"
    publish.publish(run_dir(tmp_path), out, minimum=2, streaks=previous)
    streaks = json.loads((out / "streaks.json").read_text())
    assert streaks["socks5://2.2.2.2:1080"] == stable + 1  # was there -> keep counting
    assert streaks["http://1.1.1.0:80"] == 2
    assert streaks["http://1.1.1.2:80"] == 1           # new
    assert "http://7.7.7.7:80" not in streaks          # not there this time -> streak over
    rows = {r["url"]: r for r in json.loads((out / "proxies.json").read_text())}
    assert rows["socks5://2.2.2.2:1080"]["streak"] == stable + 1
    stats = json.loads((out / "stats.json").read_text())
    assert stats["stable"] == 1 and stats["run_hours"] * stable == 24  # stable = listed for a whole day


def test_missing_or_broken_streaks_start_fresh(tmp_path):
    broken = tmp_path / "streaks.json"
    broken.write_text("[1, 2]")
    publish.publish(run_dir(tmp_path), tmp_path / "public", minimum=2, streaks=broken)
    assert set(json.loads((tmp_path / "public" / "streaks.json").read_text()).values()) == {1}


def test_streak_values_must_be_real_numbers(tmp_path):
    path = tmp_path / "streaks.json"
    path.write_text(json.dumps({"a": True, "b": 3, "c": -1, "d": "4", "e": 2.0}))
    assert publish.load_streaks(path) == {"b": 3}


def test_old_6_hour_streaks_are_converted_once(tmp_path):
    streaks = tmp_path / "streaks.json"
    streaks.write_text(json.dumps({"socks5://2.2.2.2:1080": 20}))  # 20 runs every 6 hours = 5 days
    history = tmp_path / "history.json"
    history.write_text(json.dumps([{"updated": "2026-09-26T06:17:00+00:00", "total": 900}]))  # no run_hours yet
    out = tmp_path / "public"
    publish.publish(run_dir(tmp_path), out, minimum=2, history=history, streaks=streaks)
    converted = json.loads((out / "streaks.json").read_text())["socks5://2.2.2.2:1080"]
    assert converted == 20 * 6 // publish.RUN_HOURS + 1  # still 5 days, plus this run
    assert json.loads((out / "history.json").read_text())[-1]["run_hours"] == publish.RUN_HOURS

    # the next run sees run_hours in the history and just keeps counting
    again = tmp_path / "again"
    publish.publish(run_dir(tmp_path), again, minimum=2, history=out / "history.json", streaks=out / "streaks.json")
    assert json.loads((again / "streaks.json").read_text())["socks5://2.2.2.2:1080"] == converted + 1


def _checked(i: int, confirm: str = "passed", content: str = "passed", https: str = "passed") -> CheckResult:
    from proxyscraper.checkstate import Check

    r = CheckResult(f"http 3.3.3.{i}:80", "http", f"3.3.3.{i}:80", 100 + i, "9.9.9.9", https == "passed", "elite", "DE")
    r.checks = {"basic": Check("passed"), "confirm": Check(confirm), "content": Check(content), "https": Check(https)}
    return r


def test_only_proxies_whose_checks_were_measured_and_passed_are_listed(tmp_path):
    """Listed means passed – a second request or content check that could not run is not enough."""
    rows = [_checked(1), _checked(2, confirm="unavailable"), _checked(3, content="unavailable"),
            _checked(4, https="unavailable"), _checked(5, https="failed")]
    ResultWriter(run_dir=tmp_path / "run").finalize(rows)
    (tmp_path / "run" / "run.json").write_text(json.dumps({"schema": 1, "candidates": 900, "checked": 800,
                                                           "not_checked": 100, "working": 5,
                                                           "checks": {"confirm": {"passed": 4}}}))
    out = tmp_path / "public"
    assert publish.publish(tmp_path / "run", out, minimum=1) == 0
    assert (out / "all.txt").read_text().splitlines() == ["http://3.3.3.1:80", "http://3.3.3.4:80", "http://3.3.3.5:80"]
    assert (out / "https.txt").read_text().splitlines() == ["http://3.3.3.1:80"]  # HTTPS measured and passed
    stats = json.loads((out / "stats.json").read_text())
    assert stats["held_back"] == 2 and stats["total"] == 3
    assert stats["requires"]["all.txt"] == ["basic", "confirm", "content"]
    assert stats["requires"]["https.txt"] == ["basic", "confirm", "content", "https"]
    listed = json.loads((out / "proxies.json").read_text())
    assert all(r["checks"]["confirm"]["state"] == "passed" for r in listed)
    # the run's denominators travel with the list and into the history
    assert json.loads((out / "run.json").read_text())["not_checked"] == 100
    last = json.loads((out / "history.json").read_text())[-1]
    assert (last["candidates"], last["checked"], last["not_checked"]) == (900, 800, 100)


def test_a_run_without_confirmation_publishes_nothing_and_the_old_list_stays(tmp_path):
    ResultWriter(run_dir=tmp_path / "run").finalize([_checked(i, confirm="unavailable") for i in range(1, 30)])
    out = tmp_path / "public"
    assert publish.publish(tmp_path / "run", out, minimum=20) == publish.SKIP_EXIT_CODE
    assert not out.exists()


def test_rows_from_before_checks_were_recorded_are_published_as_before(tmp_path):
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path), out, minimum=2) == 0
    stats = json.loads((out / "stats.json").read_text())
    assert stats["total"] == 4 and stats["held_back"] == 0 and not (out / "run.json").exists()


def test_the_published_csv_keeps_its_old_columns_in_place_and_adds_the_new_ones_last(tmp_path):
    import csv

    ResultWriter(run_dir=tmp_path / "run").finalize([_checked(i) for i in range(1, 4)])
    out = tmp_path / "public"
    assert publish.publish(tmp_path / "run", out, minimum=1) == 0
    with (out / "proxies.csv").open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header[13:18] == ["url", "first_seen", "uptime_24h", "uptime_7d", "works_with"]  # where 1.28 had them
    assert header[-5:] == ["checked_at", "check_basic", "check_confirm", "check_content", "check_https"]


def test_csv_cells_that_a_spreadsheet_would_run_stay_text(tmp_path):
    """The provider name comes from the ASN database (whoever registered the network): =HYPERLINK(…) there
    must not become a formula in proxies.csv – not in the run's file, not in the published one."""
    import csv

    from proxyscraper.output import csv_cell

    evil = ['=HYPERLINK("http://x.example","click")', "+1+cmd|' /C calc'!A0", "-2+3", "@SUM(1)", "\tx", "\rx"]
    rows = [_checked(i) for i in range(1, len(evil) + 1)]
    for r, org in zip(rows, evil):
        r.org = org
    ResultWriter(run_dir=tmp_path / "run").finalize(rows)
    out = tmp_path / "public"
    assert publish.publish(tmp_path / "run", out, minimum=1) == 0
    for path in (tmp_path / "run" / "proxies.csv", out / "proxies.csv"):
        with path.open(newline="", encoding="utf-8") as fh:
            orgs = sorted(row["org"] for row in csv.DictReader(fh))
        assert orgs == sorted("'" + org for org in evil), path  # once, not twice in the published copy
    numbers_and_plain_text = [-1, "-1", "+2.5", "1e-3", "ok", "", None]
    assert [csv_cell(v) for v in numbers_and_plain_text] == numbers_and_plain_text


# --------------------------------------------------------------------------- removal requests (removed.txt)

def _history_and_seen(tmp_path, now, extra):
    """A day of hourly runs, and a seen.json in which the urls in `extra` were listed in every one of them."""
    from datetime import timedelta
    runs = [{"updated": (now - timedelta(hours=h)).isoformat(timespec="seconds"), "total": 5, "https": 1,
             "by_type": {}, "median_latency": 1} for h in range(30, 0, -1)]
    history = tmp_path / "history.json"
    history.write_text(json.dumps(runs))
    seen = tmp_path / "seen.json"
    seen.write_text(json.dumps({"last_run": runs[-1]["updated"],
                                "proxies": {url: {"first_seen": runs[0]["updated"], "bits": "3fffffff"}
                                            for url in extra}}))
    return history, seen


def test_removed_addresses_are_left_out_everywhere(tmp_path):
    from proxyscraper.proxypages import page_path
    now = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)
    history, seen = _history_and_seen(tmp_path, now, ["http://7.7.7.7:80", "http://6.6.6.6:80"])
    removed = tmp_path / "removed.txt"
    removed.write_text("# comment\n1.1.1.1  # the proxy's own address\n8.8.8.0/24\n\n7.7.7.7\n")
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=now, history=history, seen=seen,
                           removed=removed) == 0
    files = [p for p in out.rglob("*") if p.is_file() and p.suffix not in (".png", ".woff2")]
    everything = "".join(p.read_text(encoding="utf-8") for p in files)
    assert "1.1.1.1:80" not in everything
    assert "2.2.2.2:1080" not in everything  # its exit IP 8.8.8.8 is in a removed network
    assert "7.7.7.7" not in everything        # listed in earlier runs: no "no longer listed" page, not in seen.json
    assert "6.6.6.6" in everything and (out / page_path("6.6.6.6:80")).exists()  # the same case, kept
    assert sorted((out / "http.txt").read_text().split()) == ["1.1.1.0:80", "1.1.1.2:80"]


def test_without_removed_txt_nothing_is_left_out(tmp_path):
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path), out, minimum=2, removed=tmp_path / "missing.txt") == 0
    assert "1.1.1.1:80" in (out / "all.txt").read_text()


def test_a_malformed_removal_line_stops_the_publish(tmp_path):
    import pytest
    removed = tmp_path / "removed.txt"
    removed.write_text("1.1.1.1\n1.1.1.300\n")
    with pytest.raises(SystemExit, match=r"removed.txt:2"):
        publish.publish(run_dir(tmp_path), tmp_path / "public", minimum=2, removed=removed)
    assert not (tmp_path / "public").exists()


def test_is_removed_reads_every_address_form():
    import ipaddress
    assert publish.load_removed(None) == []
    nets = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "2001:db8::/32")]
    assert publish.is_removed("socks5://10.1.2.3:1080", "", nets)
    assert publish.is_removed("10.1.2.3:1080", "", nets)
    assert publish.is_removed("http://[2001:db8::1]:8080", "", nets)
    assert publish.is_removed("1.2.3.4:80", "10.9.9.9", nets)
    assert not publish.is_removed("1.2.3.4:80", "", nets)
    assert not publish.is_removed("example.com:80", "not-an-ip", nets)


def test_the_repository_removal_list_parses():
    from pathlib import Path
    publish.load_removed(Path(__file__).resolve().parents[1] / "removed.txt")


# --------------------------------------------------------------------------- no third parties on the website

def test_the_website_loads_no_fonts_or_scripts_from_a_cdn(tmp_path):
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path), out, minimum=2) == 0
    pages = list(out.rglob("*.html"))
    assert len(pages) > 10
    for page in pages:
        html = page.read_text(encoding="utf-8")
        for host in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net", "unpkg.com", "cdnjs"):
            assert host not in html, f"{page.relative_to(out)} loads from {host}"
        if page.name != "legal.html" and not page.name.startswith("google"):  # not the Search Console token
            assert "legal.html" in html, f"{page.relative_to(out)} has no link to the Impressum"
    for name in ("fonts.css", "Geist-Variable.woff2", "GeistMono-Variable.woff2", "lenis.min.js", "LICENSES.txt"):
        assert (out / "vendor" / name).is_file()


def test_the_vendored_files_match_the_hashes_the_page_checks():
    import base64
    import hashlib
    import re

    from proxyscraper.publish import SITE
    html = (SITE / "index.html").read_text(encoding="utf-8")
    pinned = re.findall(r'"vendor/([\w.-]+)",\s*(?:\{ integrity: )?"(sha384-[\w+/=]+)"', html)
    assert len(pinned) == 4
    for name, sri in pinned:
        digest = base64.b64encode(hashlib.sha384((SITE / "vendor" / name).read_bytes()).digest()).decode()
        assert sri == f"sha384-{digest}", name


def test_the_imprint_is_filled_in():
    """legal.html ships with placeholders for name, address, email and the server-log sentence."""
    from proxyscraper.publish import SITE
    html = (SITE / "legal.html").read_text(encoding="utf-8")
    assert "TODO_" not in html, "fill in the Impressum in proxyscraper/site/legal.html"
