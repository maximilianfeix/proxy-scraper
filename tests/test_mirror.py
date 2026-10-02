import json
from datetime import datetime, timezone

from proxyscraper import mirror, publish

from .test_publish import run_dir

REPO = "someone/free-proxy-list"


def published(tmp_path):
    public = tmp_path / "public"
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    assert publish.publish(run_dir(tmp_path), public, minimum=2, now=now) == 0
    return public


def test_mirror_writes_lists_countries_and_readme(tmp_path):
    out = tmp_path / "list"
    message = mirror.mirror(published(tmp_path), out, REPO)
    assert message == "4 working proxies · 2026-09-24 18:00 UTC"

    assert (out / "socks5.txt").read_text(encoding="utf-8") == "2.2.2.2:1080\n"
    assert (out / "countries" / "de.txt").read_text(encoding="utf-8").splitlines() == [
        "http://1.1.1.0:80", "http://1.1.1.1:80", "http://1.1.1.2:80"]
    assert (out / "countries" / "us.txt").read_text(encoding="utf-8") == "socks5://2.2.2.2:1080\n"
    assert len(json.loads((out / "proxies.json").read_text(encoding="utf-8"))) == 4
    assert "\n" not in (out / "proxies.json").read_text(encoding="utf-8")  # compact
    # the website stays on the proxy-list branch
    assert not (out / "index.html").exists() and not (out / "country").exists()

    readme = (out / "README.md").read_text(encoding="utf-8")
    assert f"https://raw.githubusercontent.com/{REPO}/main/socks5.txt" in readme
    assert f"https://raw.githubusercontent.com/{REPO}/main/countries/de.txt" in readme
    assert "🇩🇪 Germany | 3 |" in readme
    assert "2026-09-24 18:00 UTC" in readme and "github.com/maximilianfeix/proxy-scraper" in readme

    # check that new headings are present in the Quick start section
    assert "### Python" in readme
    assert "### Node.js" in readme
    assert "### Go" in readme
    assert "### curl" in readme

    # check key contents of the new examples
    assert "dispatcher: new ProxyAgent(proxy.trim())" in readme
    assert "signal: AbortSignal.timeout(10_000)" in readme
    assert "Timeout:   10 * time.Second" in readme
    assert "Proxy: http.ProxyURL(proxyURL)" in readme
    assert 'curl -m 10 -x "socks5h://$(curl -sL' in readme
    assert 'socks5.txt | head -n 1)" https://api.ipify.org' in readme


def test_mirror_drops_countries_that_are_gone_and_keeps_foreign_files(tmp_path):
    out = tmp_path / "list"
    (out / "countries").mkdir(parents=True)
    (out / "countries" / "fr.txt").write_text("http://9.9.9.9:80\n", encoding="utf-8")
    (out / "LICENSE").write_text("MIT", encoding="utf-8")
    mirror.mirror(published(tmp_path), out, REPO)
    assert not (out / "countries" / "fr.txt").exists()
    assert (out / "LICENSE").read_text(encoding="utf-8") == "MIT"


def test_flag_and_shield():
    assert mirror.flag("de") == "🇩🇪"
    assert mirror.flag("") == "" and mirror.flag("1A") == ""
    assert mirror.shield("updated", "2026-09-24 18:00", "grey").startswith(
        "https://img.shields.io/badge/updated-2026--09--24%2018:00-grey")


def test_country_table_pads_the_last_row():
    table = mirror.country_table({"countries/de.txt": 5, "countries/us.txt": 7, "all.txt": 12}, "https://raw")
    rows = table.splitlines()
    assert len(rows) == 3
    assert rows[2].startswith("| 🇺🇸 United States | 7 |")  # most first
    assert rows[2].count("|") == rows[0].count("|")
