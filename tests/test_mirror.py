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
    assert "### Java" in readme
    assert "### Rust" in readme
    assert "### curl" in readme

    # check key contents of the new examples
    assert "dispatcher: new ProxyAgent(proxy.trim())" in readme
    assert "signal: AbortSignal.timeout(10_000)" in readme
    assert "Timeout:   10 * time.Second" in readme
    assert "Proxy: http.ProxyURL(proxyURL)" in readme
    assert "ProxySelector.of(new InetSocketAddress(uri.getHost(), uri.getPort()))" in readme
    assert 'list.lines().filter(l -> l.startsWith("http://")).toList()' in readme
    assert "reqwest::Proxy::all" in readme
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


def test_the_list_readme_names_projects_that_use_it(tmp_path):
    out = tmp_path / "list"
    mirror.mirror(published(tmp_path), out, REPO)
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "[monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker)" in readme
    assert "[gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list)" in readme


RUN = {"checked": 1000, "targets": {"basic": "checkip.example", "confirm": "confirm.example"},
       "checks": {"basic": {"passed": 40, "failed:timeout": 960}, "confirm": {"passed": 9},
                  "content": {"passed": 6}, "https": {"passed": 3}}}


def test_the_top_of_the_list_readme_has_urls_badges_and_the_mirror(tmp_path):
    out = tmp_path / "list"
    mirror.mirror(published(tmp_path), out, REPO)
    readme = (out / "README.md").read_text(encoding="utf-8")
    top = readme.split("## Download")[0]
    # copy-paste raw URLs come before everything else
    assert f"```text\nhttps://raw.githubusercontent.com/{REPO}/main/all.txt\n" in top
    assert "**4 free HTTP, SOCKS4 and SOCKS5 proxies that passed every check, re-checked every hour." in top
    assert "img.shields.io/badge/checked-every%20hour-grey" in top  # run_hours == 1 in stats.json
    assert f"img.shields.io/github/stars/{REPO}?style=social" in top
    # every list on GitHub, the CDN and the website
    assert "[proxy-scraper.de](https://proxy-scraper.de/socks5.txt)" in readme
    assert f"[CDN](https://cdn.jsdelivr.net/gh/{REPO}@main/socks5.txt)" in readme
    assert "### wget" in readme
    assert f"wget -qO http.txt https://raw.githubusercontent.com/{REPO}/main/http.txt" in readme
    assert "https://proxy-scraper.de/country/<code>/proxies.txt" in readme
    # the star ask and the chart
    assert "If this list saves you time, a ⭐ helps others find it." in readme
    assert f"api.star-history.com/svg?repos={REPO},maximilianfeix/proxy-scraper&type=Date" in readme
    # without run.json there are no invented denominators
    assert "candidates" not in readme and "## What the checks mean" in readme
    assert "| **Verified TLS** |" in readme and "| `https.txt` | – |" in readme


def test_the_list_readme_takes_its_numbers_from_the_run(tmp_path):
    public = published(tmp_path)
    (public / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    (public / "sources.json").write_text(json.dumps({"sources": [{"name": "a"}, {"name": "b"}]}), encoding="utf-8")
    out = tmp_path / "list"
    mirror.mirror(public, out, REPO)
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "This run checked **1,000** candidates, collected from **2** tracked public sources. **4** (0.40%)" in readme
    assert "fetched a page from checkip.example" in readme and "(confirm.example/html)" in readme
    assert "| every list | 40 |" in readme and "| `https.txt` | 3 |" in readme
    assert "150,000" not in readme


def test_the_list_readme_stays_honest():
    stats = {"updated": "2026-09-24T18:00:00+00:00", "total": 2, "by_type": {"http": 2}, "https": 0,
             "median_latency": 100, "requires": {"all.txt": ["basic"]}}
    text = mirror.readme(stats, {"all.txt": 2}, REPO, run=RUN)
    lowered = text.lower()
    for word in ("honeypot", "secure proxies", "safe to use", "supercharge", "seamless", "unlock"):
        assert word not in lowered
    assert "says nothing about other sites" not in text  # https is not required by any list here
    assert "img.shields.io/badge/checked-" not in text  # no run_hours, no claim about the schedule
    assert "re-checked regularly" in text
