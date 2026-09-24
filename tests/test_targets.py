import asyncio
import socket

import pytest

from proxyscraper import checker as ck
from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.options import Filters, RunOptions
from proxyscraper.targets import parse_target, target_label

from .fakes import http_forward_proxy, serve, serve_tls, socks5_forward_proxy, target_server, tls_client_context


@pytest.mark.parametrize("text, url, label", [
    ("google.com", "https://google.com/", "google.com"),
    ("https://www.google.com", "https://www.google.com/", "google.com"),
    ("http://example.org:8080/login?x=1", "http://example.org:8080/login?x=1", "example.org:8080"),
    ("https://discord.com:443/", "https://discord.com/", "discord.com"),
])
def test_parse_target(text, url, label):
    target = parse_target(text)
    assert (target.url, target.label) == (url, label)
    assert target_label(url) == label


@pytest.mark.parametrize("text", ["ftp://example.org", "https://", "http://example.org:99999/", "http://example.org:0/"])
def test_parse_target_rejects(text):
    with pytest.raises(ValueError):
        parse_target(text)


def test_target_options_roundtrip():
    argv = ["--target", "google.com", "--target", "discord.com", "--target", "google.com"]
    opts = RunOptions.from_args(parse_args(argv))
    assert opts.filters.targets == ["https://google.com/", "https://discord.com/"]  # Duplikate raus
    assert RunOptions.from_args(parse_args(opts.to_argv())) == opts
    assert opts.details and opts.filters.needs_details


def test_invalid_target_is_rejected_by_argparse(capsys):
    with pytest.raises(SystemExit):
        parse_args(["--target", "ftp://x.org"])
    assert "http" in capsys.readouterr().err


def test_filters_require_all_targets():
    f = Filters(targets=["https://a.com/", "https://b.com/"])
    r = CheckResult("http 1.1.1.1:80", "http", "1.1.1.1:80", 100, "9.9.9.9")
    r.targets = {"https://a.com/": True, "https://b.com/": False}
    assert not f.accepts(r)
    r.targets["https://b.com/"] = True
    assert f.accepts(r)
    assert "Ziel a.com, b.com" in f.describe()


@pytest.mark.parametrize("proxy_handler, ptype", [(http_forward_proxy, "http"), (socks5_forward_proxy, "socks5")])
@pytest.mark.parametrize("path, expected", [("/ok", True), ("/weiter", True), ("/gesperrt", False)])
def test_check_target_through_real_forwarding_proxy(proxy_handler, ptype, path, expected):
    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(proxy_handler)
        async with target_srv, proxy_srv:
            target = parse_target(f"http://127.0.0.1:{target_port}{path}")
            c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2)
            return await c.check_target(ptype, f"127.0.0.1:{proxy_port}", target, socket.inet_aton("127.0.0.1"))

    assert asyncio.run(go()) is expected


def test_enrich_fills_every_target(monkeypatch):
    monkeypatch.setattr(ck, "JUDGE_HOST", "127.0.0.1")  # HTTPS-Test bleibt lokal (und scheitert schnell)

    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        async with target_srv, proxy_srv:
            ok = parse_target(f"http://127.0.0.1:{target_port}/ok")
            blocked = parse_target(f"http://127.0.0.1:{target_port}/nein")
            c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2,
                           targets=[(ok, "127.0.0.1"), (blocked, "127.0.0.1")])
            r = CheckResult("x", "http", f"127.0.0.1:{proxy_port}", 100, "9.9.9.9")
            await c.enrich(r)
            return r, ok, blocked

    r, ok, blocked = asyncio.run(go())
    assert r.targets == {ok.url: True, blocked.url: False}


def test_csv_flattens_targets(tmp_path):
    from proxyscraper.output import ResultWriter

    r = CheckResult("http 1.1.1.1:80", "http", "1.1.1.1:80", 100, "9.9.9.9", True, "elite", "DE",
                    {"https://www.google.com/": True, "https://discord.com/": False})
    ResultWriter(run_dir=tmp_path / "run").finalize([r])
    csv_text = (tmp_path / "run" / "proxies.csv").read_text(encoding="utf-8")
    assert "google.com:ok;discord.com:nein" in csv_text


def test_host_header_keeps_non_default_port():
    assert parse_target("http://example.org:8080/").host_header == "example.org:8080"
    assert parse_target("https://example.org/").host_header == "example.org"

    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        async with target_srv, proxy_srv:
            target = parse_target(f"http://127.0.0.1:{target_port}/host-mit-port")
            c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2)
            return await c.check_target("http", f"127.0.0.1:{proxy_port}", target, socket.inet_aton("127.0.0.1"))

    assert asyncio.run(go()) is True


def run_tls_target(proxy_handler, ptype, path="/ok"):
    async def go():
        target_srv, target_port = await serve_tls(target_server)
        proxy_srv, proxy_port = await serve(proxy_handler)
        async with target_srv, proxy_srv:
            target = parse_target(f"https://localhost:{target_port}{path}")
            c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2)
            return await c.check_target(ptype, f"127.0.0.1:{proxy_port}", target, socket.inet_aton("127.0.0.1"))

    return asyncio.run(go())


@pytest.mark.parametrize("proxy_handler, ptype", [(http_forward_proxy, "http"), (socks5_forward_proxy, "socks5")])
@pytest.mark.parametrize("path, expected", [("/ok", True), ("/gesperrt", False)])
def test_https_target_through_tunnel_with_verified_tls(monkeypatch, proxy_handler, ptype, path, expected):
    monkeypatch.setattr(ck, "ssl_context", tls_client_context)  # dem Test-Zertifikat vertrauen
    assert run_tls_target(proxy_handler, ptype, path) is expected


def test_https_target_with_untrusted_certificate_fails():
    """Ohne Vertrauen ins Zertifikat (wie bei einem MITM-Proxy) zählt die Seite als nicht erreichbar."""
    assert run_tls_target(http_forward_proxy, "http") is False


def test_targets_without_any_success_stay_visible():
    from proxyscraper.ui import LiveStats

    stats = LiveStats({"http": 1})
    r = CheckResult("x", "http", "1.1.1.1:80", 100, "9.9.9.9")
    r.targets = {"https://www.google.com/": False}
    stats.add_details(r)
    assert stats.targets_ok == {"https://www.google.com/": 0}
    assert "https://www.google.com/" in stats.targets_ok
