"""Static pages per protocol and country for search engines, plus the sitemap (#121)."""

import html
from datetime import datetime, timezone

from proxyscraper import pages

NOW = datetime(2026, 9, 26, 9, 17, tzinfo=timezone.utc)


def row(n, ptype="http", country="DE", latency=100, **extra):
    return {"url": f"{ptype}://1.1.1.{n}:80", "proxy": f"1.1.1.{n}:80", "ptype": ptype, "country": country,
            "latency": latency, "https": False, "anonymity": "elite", "org": "Example GmbH", **extra}


ROWS = [row(1, latency=300), row(2, "socks5", latency=100, https=True), row(3, country="US"), row(4, country="DE"),
        row(5, country="FR", org='<script>alert(1)</script>')]


def test_every_page_with_its_download(tmp_path):
    pages.write_pages(ROWS, tmp_path, NOW)
    de = (tmp_path / "country" / "de" / "index.html").read_text()
    assert "<h1>Free proxies in Germany</h1>" in de and "3 proxies in Germany" in de
    assert de.index("1.1.1.2:80") < de.index("1.1.1.1:80")  # fastest first
    assert '<link rel="canonical" href="https://maximilianfeix.github.io/proxy-scraper/country/de/">' in de
    assert (tmp_path / "country" / "de" / "proxies.txt").read_text().splitlines() == [
        "socks5://1.1.1.2:80", "http://1.1.1.4:80", "http://1.1.1.1:80"]
    assert (tmp_path / "https" / "proxies.txt").read_text() == "socks5://1.1.1.2:80\n"
    assert 'href="../../logo.png"' in de and 'href="../logo.png"' in (tmp_path / "socks5" / "index.html").read_text()


def test_provider_names_are_escaped(tmp_path):
    pages.write_pages(ROWS, tmp_path, NOW)
    fr = (tmp_path / "country" / "fr" / "index.html").read_text()
    assert "<script>alert" not in fr and "&lt;script&gt;" in fr


def test_empty_countries_keep_their_page_but_stay_out_of_the_sitemap(tmp_path):
    listed = pages.write_pages(ROWS, tmp_path, NOW)
    jp = (tmp_path / "country" / "jp" / "index.html").read_text()
    assert "No proxies in Japan passed every check" in jp and "<table" not in jp
    sitemap = (tmp_path / "sitemap.xml").read_text()
    assert "country/de/" in listed and "country/us/" not in listed  # 1 proxy is below SITEMAP_MIN
    assert "<loc>https://maximilianfeix.github.io/proxy-scraper/</loc>" in sitemap
    assert "country/jp/" not in sitemap and "socks4/" in sitemap and "2026-09-26T09:17:00+00:00" in sitemap


def test_pages_link_to_each_other(tmp_path):
    pages.write_pages(ROWS, tmp_path, NOW)
    socks5 = (tmp_path / "socks5" / "index.html").read_text()
    assert '<a href="../socks5/" aria-current="page">SOCKS5 (1)</a>' in socks5
    assert '<a href="../country/de/">Germany (3)</a>' in socks5
    assert "Japan" not in socks5  # empty countries aren't linked


def test_filter_button_opens_the_list_with_the_same_filter(tmp_path):
    pages.write_pages(ROWS, tmp_path, NOW)
    expected = {"socks5": "?types=socks5", "https": "?https=1", "elite": "?elite=1", "country/de": "?country=DE"}
    for path, query in expected.items():
        html = (tmp_path / path / "index.html").read_text(encoding="utf-8")
        assert f'href="{"../" * (path.count("/") + 1)}{query}#list">Filter the full list' in html


def test_a_country_page_has_the_numbers_commands_and_answers(tmp_path):
    import json
    import re
    rows = [row(1, "socks5", https=True, uptime_7d=95, speed_kbps=400, sites={"google": True}),
            row(2, "http", https=False, uptime_7d=20),
            row(3, "http", country="US")]
    pages.write_pages(rows, tmp_path, NOW)
    de = (tmp_path / "country" / "de" / "index.html").read_text(encoding="utf-8")
    facts = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", de))
    assert "2 working right now" in facts and "1 tunnel HTTPS" in facts and "1 on the list 90 %+ of the week" in facts
    assert "1 get through to Google" in facts and "400 KB/s" in facts
    assert "proxy-scraper --pick 5 --country DE" in de and 'curl -x "$(proxy-scraper --pick --country DE' in de
    assert ">Speed<" in de and ">Uptime<" in de
    ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', de, re.S)]
    faq = next(d for d in ld if d["@type"] == "FAQPage")
    assert any("Germany" in q["name"] for q in faq["mainEntity"])


def test_protocol_pages_pick_by_protocol(tmp_path):
    pages.write_pages([row(1, "socks5", https=True)], tmp_path, NOW)
    assert "proxy-scraper --pick 5 --types socks5" in (tmp_path / "socks5" / "index.html").read_text()
    assert "proxy-scraper --pick 5 --https-only" in (tmp_path / "https" / "index.html").read_text()
    assert "proxy-scraper --pick 5 --anonymity elite" in (tmp_path / "elite" / "index.html").read_text()


def test_an_empty_page_still_renders(tmp_path):
    pages.write_pages([], tmp_path, NOW)
    assert "No proxies in Germany" in (tmp_path / "country" / "de" / "index.html").read_text()


def test_the_median_speed_is_the_real_median():
    assert pages._facts([row(1, speed_kbps=100), row(2, speed_kbps=400)])["speed"] == 250


def test_pages_dont_claim_google_blocked_proxies_that_were_never_checked(tmp_path):
    pages.write_pages([row(1, "socks4"), row(2, "socks4")], tmp_path, NOW)
    page = html.unescape((tmp_path / "socks4" / "index.html").read_text(encoding="utf-8"))
    assert "none of them got through" not in page and "<dd>get through to Google</dd>" not in page
    assert "weren't part of the last site check" in page
