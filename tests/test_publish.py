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
    everything = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
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
    html = SITE.read_text(encoding="utf-8")
    assert "proxies.json" in html and "history.json" in html and "<script" in html


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
    previous.write_text(json.dumps({"socks5://2.2.2.2:1080": 5, "http://1.1.1.0:80": 1, "http://7.7.7.7:80": 9,
                                    "kaputt": "x"}))
    out = tmp_path / "public"
    publish.publish(run_dir(tmp_path), out, minimum=2, streaks=previous)
    streaks = json.loads((out / "streaks.json").read_text())
    assert streaks["socks5://2.2.2.2:1080"] == 6       # was there -> keep counting
    assert streaks["http://1.1.1.0:80"] == 2
    assert streaks["http://1.1.1.2:80"] == 1           # new
    assert "http://7.7.7.7:80" not in streaks          # not there this time -> streak over
    rows = {r["url"]: r for r in json.loads((out / "proxies.json").read_text())}
    assert rows["socks5://2.2.2.2:1080"]["streak"] == 6
    assert json.loads((out / "stats.json").read_text())["stable"] == 1  # only the one with 6 runs (>= 4)


def test_missing_or_broken_streaks_start_fresh(tmp_path):
    broken = tmp_path / "streaks.json"
    broken.write_text("[1, 2]")
    publish.publish(run_dir(tmp_path), tmp_path / "public", minimum=2, streaks=broken)
    assert set(json.loads((tmp_path / "public" / "streaks.json").read_text()).values()) == {1}


def test_streak_values_must_be_real_numbers(tmp_path):
    path = tmp_path / "streaks.json"
    path.write_text(json.dumps({"a": True, "b": 3, "c": -1, "d": "4", "e": 2.0}))
    assert publish.load_streaks(path) == {"b": 3}
