"""Python-API: Optionen landen richtig im Lauf, die Ausgabe bleibt still, want wird eingehalten."""

import asyncio

import proxyscraper
from proxyscraper import api
from proxyscraper.checker import CheckResult
from proxyscraper.ui import widgets


class FakeRun:
    seen = []

    def __init__(self, opts, show_banner=True):
        FakeRun.seen.append(opts)
        self.kept = [CheckResult(f"http 1.1.1.{i}:80", "http", f"1.1.1.{i}:80", 500 - i * 100, "9.9.9.9")
                     for i in range(4)]

    async def execute(self):
        widgets.console.print("das darf niemand sehen")
        return 0


def test_find_proxies_passes_filters_and_keeps_quiet(monkeypatch, capsys):
    from proxyscraper import app
    monkeypatch.setattr(app, "Run", FakeRun)
    FakeRun.seen.clear()
    result = proxyscraper.find_proxies(want=2, https=True, countries="de,at", types=["socks5"],
                                       anonymity="elite", no_datacenter=True, targets=["https://example.com/"])
    opts = FakeRun.seen[0]
    assert opts.types == ["socks5"] and opts.want == 2
    f = opts.filters
    assert f.https_only and f.countries == {"DE", "AT"} and f.min_anonymity == "elite" and f.no_datacenter
    assert [r.latency for r in result] == [200, 300]  # schnellste zuerst, genau `want` Stück
    assert "niemand" not in capsys.readouterr().out


def test_check_proxies_writes_a_temporary_list(monkeypatch):
    from proxyscraper import app
    seen = {}

    class Recheck(FakeRun):
        def __init__(self, opts, show_banner=True):
            super().__init__(opts, show_banner)
            with open(opts.recheck, encoding="utf-8") as fh:
                seen["lines"] = fh.read().splitlines()
            seen["path"] = opts.recheck

    monkeypatch.setattr(app, "Run", Recheck)
    result = asyncio.run(api.check_proxies_async(["socks5://1.2.3.4:1080", "5.6.7.8:3128", "  ", ""]))
    assert seen["lines"] == ["socks5://1.2.3.4:1080", "http://5.6.7.8:3128"]
    assert len(result) == 4
    import os
    assert not os.path.exists(seen["path"])  # aufgeräumt


def test_url_property():
    r = CheckResult("socks5 1.2.3.4:1080", "socks5", "1.2.3.4:1080", 100, "9.9.9.9")
    assert r.url == "socks5://1.2.3.4:1080"


def test_lazy_exports():
    assert proxyscraper.find_proxies is api.find_proxies
    import pytest
    with pytest.raises(AttributeError):
        proxyscraper.does_not_exist  # noqa: B018
