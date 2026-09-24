import json
from datetime import datetime

import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.exporters import EXPORTERS, clash, curl, parse_exports, proxychains
from proxyscraper.options import RunOptions
from proxyscraper.output import ResultWriter

NOW = datetime(2026, 9, 24, 18, 0)


def result(ptype, proxy, latency=100, country="DE"):
    return CheckResult(f"{ptype} {proxy}", ptype, proxy, latency, "9.9.9.9", https=True, country=country)


ROWS = [
    result("socks5", "203.0.113.10:1080", 90),
    result("http", "198.51.100.24:8080", 180, country=""),
    result("socks4", "192.0.2.40:4145", 300),
]


def test_proxychains_config():
    conf = proxychains(ROWS, NOW)
    assert "random_chain" in conf and "proxy_dns" in conf
    entries = conf.split("[ProxyList]\n", 1)[1].splitlines()
    assert entries == ["socks5 203.0.113.10 1080", "http 198.51.100.24 8080", "socks4 192.0.2.40 4145"]


def test_clash_skips_socks4_and_builds_a_group():
    text = clash(ROWS, NOW)
    assert "192.0.2.40" not in text  # Clash kennt kein SOCKS4
    assert '    server: "203.0.113.10"\n    port: 1080' in text
    assert '  - name: "?? http 198.51.100.24:8080"' in text  # ohne Land
    assert "type: url-test" in text and "  - MATCH,proxy-scraper" in text
    group = text.split("    proxies:\n", 1)[1].split("rules:", 1)[0].splitlines()
    names = [json.loads(line.strip()[2:]) for line in group]
    assert names == ["DE socks5 203.0.113.10:1080", "?? http 198.51.100.24:8080"]


def test_clash_is_valid_yaml():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(clash(ROWS, NOW))
    assert [p["type"] for p in data["proxies"]] == ["socks5", "http"]
    assert data["proxy-groups"][0]["proxies"] == [p["name"] for p in data["proxies"]]


def test_clash_without_usable_proxies():
    assert clash([result("socks4", "192.0.2.40:4145")], NOW).endswith("proxies: []\n")


def test_curl_uses_remote_dns_for_socks5():
    assert curl(ROWS, NOW).splitlines() == [
        "socks5h://203.0.113.10:1080", "http://198.51.100.24:8080", "socks4://192.0.2.40:4145"]


@pytest.mark.parametrize("value, expected", [
    ("clash", ["clash"]),
    ("curl, proxychains,clash", ["proxychains", "clash", "curl"]),
    ("CLASH,clash", ["clash"]),
    ("all", list(EXPORTERS)),
])
def test_parse_exports(value, expected):
    assert parse_exports(value) == expected


def test_unknown_format_is_rejected(capsys):
    with pytest.raises(SystemExit):
        parse_args(["--export", "clash,v2ray"])
    assert "v2ray" in capsys.readouterr().err
    with pytest.raises(ValueError):
        RunOptions(exports=["v2ray"])
    with pytest.raises(ValueError, match="v2ray"):
        parse_exports("all,v2ray")  # "all" darf keinen Tippfehler verdecken


def test_writer_writes_requested_formats(tmp_path):
    files = ResultWriter(run_dir=tmp_path / "run", exports=["proxychains", "curl"]).finalize(ROWS)
    assert (tmp_path / "run" / "proxychains.conf").exists() and (tmp_path / "run" / "curl.txt").exists()
    assert not (tmp_path / "run" / "clash.yaml").exists()
    assert files["curl (curl.txt)"] == tmp_path / "run" / "curl.txt"


def test_http_proxies_without_connect_are_left_out_where_everything_is_tunnelled():
    plain = CheckResult("http 192.0.2.80:80", "http", "192.0.2.80:80", 50, "9.9.9.9", https=False)
    untested = CheckResult("http 192.0.2.81:80", "http", "192.0.2.81:80", 60, "9.9.9.9")  # --fast
    rows = [plain, untested, *ROWS]
    assert "192.0.2.80" not in proxychains(rows, NOW) and "192.0.2.80" not in clash(rows, NOW)
    assert "192.0.2.81" in proxychains(rows, NOW) and "192.0.2.81" in clash(rows, NOW)
    assert "192.0.2.80" in curl(rows, NOW)  # curl kann auch einfaches HTTP ohne Tunnel
