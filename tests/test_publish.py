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

    assert (out / "all.txt").read_text().splitlines()[0] == "socks5://2.2.2.2:1080"  # schnellster zuerst
    assert (out / "http.txt").read_text().splitlines() == ["1.1.1.0:80", "1.1.1.1:80", "1.1.1.2:80"]
    assert (out / "socks5.txt").read_text() == "2.2.2.2:1080\n"
    assert (out / "socks4.txt").read_text() == ""
    assert len((out / "https.txt").read_text().splitlines()) == 3
    assert len((out / "elite.txt").read_text().splitlines()) == 2

    total = json.loads((out / "badges" / "total.json").read_text())
    assert total == {"schemaVersion": 1, "label": "funktionierende Proxys", "message": "4", "color": "brightgreen"}
    stats = json.loads((out / "stats.json").read_text())
    assert stats["by_type"] == {"http": 3, "socks4": 0, "socks5": 1}
    assert stats["countries"] == {"DE": 3, "US": 1}

    readme = (out / "README.md").read_text()
    assert "24.09.2026 18:00 UTC" in readme and "Latenz, Land, HTTPS, Anonymität" in readme
    assert "raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt" in readme
    assert "**4** funktionierende Proxys" in summary.read_text()


def test_publish_skips_when_too_few(tmp_path):
    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path, n=0), out, minimum=20) == publish.SKIP_EXIT_CODE
    assert not out.exists()


def test_num():
    assert publish.num(1234567) == "1.234.567"
