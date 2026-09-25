import asyncio
import socket

import pytest

from proxyscraper import checker as ck
from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.judges import Judge
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
    assert "target a.com, b.com" in f.describe()


@pytest.mark.parametrize("proxy_handler, ptype", [(http_forward_proxy, "http"), (socks5_forward_proxy, "socks5")])
@pytest.mark.parametrize("path, expected", [("/ok", True), ("/redirect", True), ("/blocked", False)])
def test_check_target_through_real_forwarding_proxy(proxy_handler, ptype, path, expected):
    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(proxy_handler)
        async with target_srv, proxy_srv:
            target = parse_target(f"http://127.0.0.1:{target_port}{path}")
            c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2)
            return await c.check_target(ptype, f"127.0.0.1:{proxy_port}", target, socket.inet_aton("127.0.0.1"))

    assert asyncio.run(go()) is expected


def test_enrich_fills_every_target():

    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        async with target_srv, proxy_srv:
            ok = parse_target(f"http://127.0.0.1:{target_port}/ok")
            blocked = parse_target(f"http://127.0.0.1:{target_port}/no")
            # local check target: the HTTPS test stays on localhost (and fails fast)
            c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2, judge=Judge("127.0.0.1"),
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
    assert "google.com:ok;discord.com:no" in csv_text


def test_host_header_keeps_non_default_port():
    assert parse_target("http://example.org:8080/").host_header == "example.org:8080"
    assert parse_target("https://example.org/").host_header == "example.org"

    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        async with target_srv, proxy_srv:
            target = parse_target(f"http://127.0.0.1:{target_port}/host-with-port")
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
    monkeypatch.setattr(ck, "ssl_context", tls_client_context)  # trust the test certificate
    assert run_tls_target(proxy_handler, ptype, path) is expected


def test_https_target_with_untrusted_certificate_fails():
    """Without trust in the certificate (like with a MITM proxy) the site counts as unreachable."""
    assert run_tls_target(http_forward_proxy, "http") is False


def test_targets_without_any_success_stay_visible():
    from proxyscraper.ui import LiveStats

    stats = LiveStats({"http": 1})
    r = CheckResult("x", "http", "1.1.1.1:80", 100, "9.9.9.9")
    r.targets = {"https://www.google.com/": False}
    stats.add_details(r)
    assert list(stats.targets_ok.items()) == [("https://www.google.com/", 0)]


def test_detail_connections_are_bounded(monkeypatch):
    """Many simultaneous hits must not open unlimited connections (EMFILE)."""
    monkeypatch.setattr(ck, "DETAIL_CONNECTIONS", 4)
    active = peak = 0

    async def slow_check(self, ptype, proxy):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return True

    monkeypatch.setattr(ck.Checker, "check_https", slow_check)

    async def go():
        c = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2)
        results = [CheckResult(f"http 1.1.1.{i}:80", "http", f"1.1.1.{i}:80", 100, "9.9.9.9") for i in range(40)]
        await asyncio.gather(*(c.enrich(r) for r in results))
        return results

    results = asyncio.run(go())
    assert all(r.https for r in results)
    assert peak == 4


def test_labels_distinguish_http_and_https_of_the_same_site():
    urls = ["http://example.org/", "https://example.org/"]
    assert [target_label(u, urls) for u in urls] == ["http://example.org", "https://example.org"]
    assert target_label("https://example.org/", ["https://other.org/"]) == "example.org"


def test_failing_socks_handshake_closes_the_socket(monkeypatch):
    """If the handshake fails with an exception, the socket must not stay open."""
    closed = []

    class FakeWriter:
        def close(self):
            closed.append(True)

    async def fake_connect(self, proxy, detail=False):
        return object(), FakeWriter()

    async def broken_handshake(self, *args):
        raise asyncio.IncompleteReadError(b"", 2)

    monkeypatch.setattr(ck.Checker, "_connect", fake_connect)
    monkeypatch.setattr(ck.Checker, "_handshake", broken_handshake)
    c = ck.Checker("3.3.3.3", set(), timeout=2, connect_timeout=1)
    with pytest.raises(asyncio.IncompleteReadError):
        asyncio.run(c.check_target("socks5", "1.1.1.1:1080", parse_target("http://example.org/"), b"\x01" * 4))
    assert closed == [True]


@pytest.mark.parametrize("resolvable, expected", [(True, True), (False, False)])
def test_startup_resolves_targets(monkeypatch, resolvable, expected):
    from proxyscraper import app

    async def go():
        loop = asyncio.get_running_loop()

        async def fake_getaddrinfo(host, port, family=0):
            if not resolvable:
                raise OSError("unbekannt")
            return [(None, None, None, "", ("93.184.216.34", port))]

        monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
        run = app.Run(RunOptions(filters=Filters(targets=["https://example.org/"])), show_banner=False)
        ok = await run.resolve_targets()
        return ok, run.targets

    ok, targets = asyncio.run(go())
    assert ok is expected
    assert [(t.host, ip) for t, ip in targets] == ([("example.org", "93.184.216.34")] if expected else [])


def test_fast_mode_skips_https_test_but_checks_targets(tmp_path):
    """--fast --target: no HTTPS test, target sites yes – and the hits are still saved."""
    import contextlib

    from proxyscraper import pipeline
    from proxyscraper.geo import GeoResolver
    from proxyscraper.output import ResultWriter
    from proxyscraper.ui import CheckDashboard, LiveStats

    async def go():
        target_srv, target_port = await serve(target_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        async with target_srv, proxy_srv:
            target = parse_target(f"http://127.0.0.1:{target_port}/ok")
            opts = RunOptions(fast=True, no_geo=True, filters=Filters(targets=[target.url]))
            checker = ck.Checker("3.3.3.3", set(), timeout=3, connect_timeout=2, targets=[(target, "127.0.0.1")],
                                 https_test=False)

            async def fake_check(key):
                return CheckResult(key, "http", f"127.0.0.1:{proxy_port}", 100, "9.9.9.9")

            async def always(r):
                return True

            checker.check, checker.confirm = fake_check, always
            stats = LiveStats({"http": 1})
            writer = ResultWriter(run_dir=tmp_path / "run")
            run = await pipeline.run_checks([f"http 127.0.0.1:{proxy_port}"], checker, opts,
                                            CheckDashboard(stats, writer.live_path, 1, opts.details), writer,
                                            GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext())
            return run, writer, target

    run, writer, target = asyncio.run(go())
    r = run.results[0]
    assert r.https is None and r.targets == {target.url: True}
    assert writer.live_path.read_text(encoding="utf-8").strip().startswith("http://127.0.0.1:")


def test_csv_labels_distinguish_http_and_https(tmp_path):
    from proxyscraper.output import ResultWriter

    r = CheckResult("x", "http", "1.1.1.1:80", 100, "9.9.9.9",
                    targets={"http://example.org/": True, "https://example.org/": False})
    ResultWriter(run_dir=tmp_path / "run").finalize([r])
    assert "http://example.org:ok;https://example.org:no" in (tmp_path / "run" / "proxies.csv").read_text(
        encoding="utf-8")
