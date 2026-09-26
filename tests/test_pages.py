"""Static pages per protocol and country for search engines, plus the sitemap (#121)."""

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
