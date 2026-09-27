"""A page per proxy: its details, a 7-day timeline and commands to test it yourself."""

from datetime import datetime, timedelta, timezone

from proxyscraper import proxypages

NOW = datetime(2026, 9, 27, 12, 17, tzinfo=timezone.utc)
RUNS = [NOW - timedelta(hours=h) for h in range(47, -1, -1)]  # 48 hourly runs, this one last


def row(ip, ptype="socks5", **extra):
    base = {"url": f"{ptype}://{ip}:1080", "proxy": f"{ip}:1080", "ptype": ptype, "latency": 250, "https": True,
            "anonymity": "elite", "country": "DE", "org": "Example GmbH", "asn": 64500, "hosting": True,
            "blocklisted": False, "exit_ip": ip, "uptime_7d": 96, "uptime_24h": 100,
            "first_seen": "2026-09-25T12:17:00+00:00", "sites": {"google": True, "reddit": False}}
    base.update(extra)
    return base


def test_one_page_per_address_with_every_protocol(tmp_path):
    rows = [row("8.8.8.8"), row("8.8.8.8", "http", https=False), row("9.9.9.9", org="<b>Evil</b>")]
    proxypages.write_proxy_pages(rows, tmp_path, NOW, {}, RUNS)
    page = (tmp_path / "proxy" / "8.8.8.8-1080" / "index.html").read_text(encoding="utf-8")
    assert "socks5://8.8.8.8:1080" in page and "http://8.8.8.8:1080" in page
    assert "Germany" in page and "Example GmbH" in page and "AS64500" in page
    assert "Google" in page and "96 %" in page
    evil = (tmp_path / "proxy" / "9.9.9.9-1080" / "index.html").read_text(encoding="utf-8")
    assert "<b>Evil</b>" not in evil and "&lt;b&gt;Evil&lt;/b&gt;" in evil


def test_test_commands_fit_the_protocol(tmp_path):
    rows = [row("8.8.8.8"), row("7.7.7.7", "http", https=False), row("6.6.6.6", "socks4")]
    proxypages.write_proxy_pages(rows, tmp_path, NOW, {}, RUNS)

    def page(ip):
        return (tmp_path / "proxy" / f"{ip}-1080" / "index.html").read_text(encoding="utf-8")
    assert "curl -x socks5h://8.8.8.8:1080 https://api.ipify.org" in page("8.8.8.8")
    assert "curl -x http://7.7.7.7:1080 http://api.ipify.org" in page("7.7.7.7")  # no HTTPS through this one
    assert "curl -x socks4://6.6.6.6:1080 https://api.ipify.org" in page("6.6.6.6")


def test_only_reliable_proxies_are_indexed(tmp_path):
    rows = [row("8.8.8.8", uptime_7d=96), row("9.9.9.9", uptime_7d=10), row("5.5.5.5", uptime_7d=None)]
    indexed = proxypages.write_proxy_pages(rows, tmp_path, NOW, {}, RUNS)
    assert indexed == ["proxy/8.8.8.8-1080/"]
    assert 'name="robots" content="noindex"' in (tmp_path / "proxy" / "9.9.9.9-1080" / "index.html").read_text()
    assert "noindex" not in (tmp_path / "proxy" / "8.8.8.8-1080" / "index.html").read_text()


def test_timeline_marks_the_runs_it_was_listed_in(tmp_path):
    bits = 0b101  # this run and the one two hours ago
    proxypages.write_proxy_pages([row("8.8.8.8")], tmp_path, NOW, {"socks5://8.8.8.8:1080": bits}, RUNS)
    page = (tmp_path / "proxy" / "8.8.8.8-1080" / "index.html").read_text(encoding="utf-8")
    assert page.count('class="cell on"') == 2 and page.count('class="cell"') == len(RUNS) - 2


def test_the_list_pages_link_to_the_proxy_pages(tmp_path):
    from proxyscraper import pages
    pages.write_pages([row("8.8.8.8")], tmp_path, NOW)
    assert 'href="../proxy/8.8.8.8-1080/"' in (tmp_path / "socks5" / "index.html").read_text(encoding="utf-8")


def test_pages_share_one_stylesheet(tmp_path):
    proxypages.write_proxy_pages([row("8.8.8.8")], tmp_path, NOW, {}, RUNS)
    page = (tmp_path / "proxy" / "8.8.8.8-1080" / "index.html").read_text()
    assert '<link rel="stylesheet" href="../style.css">' in page
    assert ".timeline" in (tmp_path / "proxy" / "style.css").read_text()
