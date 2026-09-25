"""Proxys, die Inhalte verändern: ehrlicher Proxy, Skript-Einschleuser, Fehlerseite, keine Referenz."""

import asyncio

import pytest

from proxyscraper import checker as ck
from proxyscraper.checker import CheckResult, page_hash

PAGE = b"<!DOCTYPE html><html><body><h1>Herman Melville - Moby-Dick</h1></body></html>"
REFERENCE = page_hash(PAGE)
INJECTED = PAGE.replace(b"</body>", b'<script src="http://203.0.113.9/Reportal.js"></script></body>')


def fake_proxy(answer_html: bytes, status: bytes = b"200 OK"):
    async def handler(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        if head.startswith(b"GET http://httpbin.org/html "):
            writer.write(b"HTTP/1.1 " + status + b"\r\nContent-Length: %d\r\n\r\n" % len(answer_html) + answer_html)
        else:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()
    return handler


def tampers(handler, reference=REFERENCE):
    async def go():
        srv = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        c = ck.Checker("3.3.3.3", set(), timeout=2, connect_timeout=1, confirm_ip="4.4.4.4",
                       integrity_reference=reference)
        try:
            return await c.tampers(CheckResult("x", "http", f"127.0.0.1:{port}", 100, "9.9.9.9"))
        finally:
            srv.close()
    return asyncio.run(go())


def test_honest_proxy_passes():
    assert tampers(fake_proxy(PAGE)) is False


def test_injected_script_is_caught():
    assert tampers(fake_proxy(INJECTED)) is True


def test_emptied_page_is_caught():
    assert tampers(fake_proxy(b"")) is True


@pytest.mark.parametrize("status", [b"403 Forbidden", b"502 Bad Gateway"])
def test_error_pages_are_not_called_tampering(status):
    # sagt nichts über Manipulation – darum kümmern sich Bestätigung und Zielseiten
    assert tampers(fake_proxy(b"blocked", status)) is False


def test_without_reference_nothing_is_judged():
    assert tampers(fake_proxy(INJECTED), reference=None) is False


def test_missing_reference_is_reported(monkeypatch):
    from proxyscraper import app
    from proxyscraper.judges import Judge, JudgeProbe
    from proxyscraper.options import RunOptions

    async def ranked():
        return [JudgeProbe(Judge("a"), "1.1.1.1", 10, "87.150.19.11")]

    async def own():
        return ["87.150.19.11"]

    async def confirm():
        return "4.4.4.4"

    async def no_reference(timeout):
        return None

    notes = []
    monkeypatch.setattr(app, "rank_judges", ranked)
    monkeypatch.setattr(app, "get_own_ips", own)
    monkeypatch.setattr(app, "confirm_target", confirm)
    monkeypatch.setattr(app, "integrity_reference", no_reference)
    monkeypatch.setattr(app, "note", lambda text, *a: notes.append(text))
    assert asyncio.run(app.Run(RunOptions(no_geo=True), show_banner=False).prepare_network())
    assert any("Inhalte verändern" in n for n in notes)


def test_reference_needs_verified_https():
    calls = []

    async def fetch(url, **kw):
        calls.append((url, kw))
        return 200, {}, PAGE

    assert asyncio.run(ck.integrity_reference(timeout=1, fetch=fetch)) == REFERENCE
    url, kw = calls[0]
    assert url == "https://httpbin.org/html" and kw["insecure_fallback"] is False


def test_tampering_proxies_are_dropped_and_counted(tmp_path):
    import contextlib

    from proxyscraper import output, pipeline
    from proxyscraper.geo import GeoResolver
    from proxyscraper.options import RunOptions
    from proxyscraper.ui import CheckDashboard, LiveStats

    class Checker:
        async def check(self, key):
            ptype, proxy = key.split(" ")
            return CheckResult(key, ptype, proxy, 100, "9.9.9.9")

        async def confirm(self, r):
            return True

        async def tampers(self, r):
            return r.proxy.startswith("2.")  # 2.x schleust etwas ein

        async def enrich(self, r):
            r.https = True

    async def go():
        jobs = ["http 1.1.1.1:80", "http 2.2.2.2:80"]
        stats = LiveStats({"http": 2})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 2, True)
        run = await pipeline.run_checks(jobs, Checker(), RunOptions(no_geo=True), dashboard, writer,
                                        GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext())
        return run, stats

    run, stats = asyncio.run(go())
    assert run.working == {"http 1.1.1.1:80"} and stats.tampered == 1
    assert "http 2.2.2.2:80" in run.checked  # zählt für die Quelle als Fehlschlag
