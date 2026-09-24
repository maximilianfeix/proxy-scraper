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
    assert "24.09.2026 18:00 UTC" in readme and "Latenz, Land, HTTPS, Anonymität" in readme
    assert "raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt" in readme
    assert "**4** funktionierende Proxys" in summary.read_text(encoding="utf-8")


def test_publish_skips_when_too_few(tmp_path):
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path, n=0), out, minimum=20) == publish.SKIP_EXIT_CODE
    assert not out.exists()


def test_median_latency_for_even_count():
    rows = [{"latency": ms, "ptype": "http"} for ms in (100, 200, 300, 400)]
    assert publish.stats_for(rows, datetime.now(timezone.utc))["median_latency"] == 250


def test_num():
    assert publish.num(1234567) == "1.234.567"
