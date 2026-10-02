"""--export pac and the live list's proxy.pac (#242)."""

import json
import shutil
import subprocess
from dataclasses import replace

import pytest

from proxyscraper.exporters import EXPORTERS, pac, parse_exports

from .test_exporters import NOW, ROWS, result

NODE = shutil.which("node")


def find_proxy(script, url, host):
    """Runs FindProxyForURL like a browser would, with the PAC helper functions it may use."""
    harness = f"""
const shExpMatch = (s, p) => new RegExp("^" + p.replace(/[.+^${{}}()|[\\]\\\\]/g, "\\\\$&")
  .replace(/\\*/g, ".*").replace(/\\?/g, ".") + "$").test(s);
const isPlainHostName = (h) => !h.includes(".");
const dnsResolve = () => {{ throw new Error("the PAC must not resolve host names"); }};
const isInNet = () => {{ throw new Error("the PAC must not resolve host names"); }};
{script}
process.stdout.write(FindProxyForURL({json.dumps(url)}, {json.dumps(host)}));
"""
    return subprocess.run([NODE, "-e", harness], check=True, capture_output=True, text=True).stdout


def test_entries_best_first_with_the_right_keywords():
    text = pac(ROWS, NOW)
    assert "PROXY 198.51.100.24:8080" in text and "SOCKS5 203.0.113.10:1080" in text and "SOCKS 192.0.2.40:4145" in text
    assert text.index("SOCKS5 203.0.113.10:1080") < text.index("PROXY 198.51.100.24:8080")  # rows come best first


def test_no_direct_fallback_after_the_proxies():
    """When every proxy is down the browser must not quietly fall back to the real IP."""
    text = pac(ROWS, NOW)
    chain = text.split('const PROXIES = "', 1)[1].split('"', 1)[0]
    assert "DIRECT" not in chain


def test_leaves_out_what_a_pac_cant_use():
    rows = [
        result("http", "user:pass@198.51.100.1:8080"),  # PAC has no way to carry a login
        replace(result("http", "198.51.100.2:8080"), https=False),  # no CONNECT – no https:// pages
        result("socks5", "203.0.113.3:1080"),
    ]
    text = pac(rows, NOW)
    assert "198.51.100.1" not in text and "198.51.100.2" not in text and "SOCKS5 203.0.113.3:1080" in text


def test_keeps_the_list_short():
    rows = [result("socks5", f"203.0.113.{i}:1080") for i in range(60)]
    assert pac(rows, NOW).count("SOCKS5 ") == 30


def test_listed_as_an_export_format():
    assert EXPORTERS["pac"][0] == "proxy.pac"
    assert "pac" in parse_exports("all") and parse_exports("pac") == ["pac"]


@pytest.mark.skipif(not NODE, reason="needs node to run the PAC like a browser")
@pytest.mark.parametrize("url,host,direct", [
    ("https://example.com/", "example.com", False),
    ("http://localhost:3000/", "localhost", True),
    ("http://intranet/", "intranet", True),
    ("http://127.0.0.1:8899/", "127.0.0.1", True),
    ("http://10.1.2.3/", "10.1.2.3", True),
    ("http://192.168.0.10/", "192.168.0.10", True),
    ("http://172.20.0.5/", "172.20.0.5", True),
    ("http://172.40.0.5/", "172.40.0.5", False),  # public, despite the 172.
    ("http://printer.local/", "printer.local", True),
])
def test_runs_in_a_browser_like_runtime(url, host, direct):
    answer = find_proxy(pac(ROWS, NOW), url, host)
    if direct:
        assert answer == "DIRECT"
    else:
        assert answer.split("; ") == ["SOCKS5 203.0.113.10:1080", "PROXY 198.51.100.24:8080", "SOCKS 192.0.2.40:4145"]


@pytest.mark.skipif(not NODE, reason="needs node to run the PAC like a browser")
def test_without_proxies_it_fails_closed_instead_of_going_direct():
    # an empty answer means DIRECT in Chrome – a proxy that never answers keeps the real IP out of it
    assert find_proxy(pac([], NOW), "https://example.com/", "example.com") == "PROXY 127.0.0.1:1"


def test_the_live_list_publishes_proxy_pac(tmp_path):
    from datetime import timezone

    from proxyscraper import publish

    from .test_publish import run_dir

    out = tmp_path / "public"
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=NOW.replace(tzinfo=timezone.utc)) == 0
    text = (out / "proxy.pac").read_text(encoding="utf-8")
    assert "function FindProxyForURL" in text
    assert text.index("SOCKS5 2.2.2.2:1080") < text.index("PROXY 1.1.1.0:80")  # best first, like all.txt
