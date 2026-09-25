"""Python-API: Optionen landen richtig im Lauf, die Ausgabe bleibt still, want wird eingehalten."""

import asyncio

import pytest

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
    result = api.find_proxies(want=2, https=True, countries="de,at", types=["socks5"],
                              anonymity="elite", no_datacenter=True, targets=["example.com", "https://example.com/"])
    opts = FakeRun.seen[0]
    assert opts.types == ["socks5"] and opts.want == 2
    f = opts.filters
    assert f.https_only and f.countries == {"DE", "AT"} and f.min_anonymity == "elite" and f.no_datacenter
    assert f.targets == ["https://example.com/"]  # wie in der CLI normalisiert, doppelte raus
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
    # in einem frischen Prozess: hier ist api längst importiert
    import subprocess
    import sys
    code = ("import sys, proxyscraper; assert 'proxyscraper.api' not in sys.modules; "
            "f = proxyscraper.find_proxies; assert 'proxyscraper.api' in sys.modules; "
            "assert not hasattr(proxyscraper, 'does_not_exist')")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_bad_arguments_fail_early():
    with pytest.raises(ValueError):
        api.find_proxies(anonymity="transparent")
    with pytest.raises(ValueError):
        api.find_proxies(targets=["ftp://example.com"])


def test_overlapping_calls_run_one_after_another(monkeypatch, capsys):
    from proxyscraper import app
    running, most = [0], [0]

    class Slow(FakeRun):
        async def execute(self):
            running[0] += 1
            most[0] = max(most[0], running[0])
            await asyncio.sleep(0.1)
            widgets.console.print("das darf niemand sehen")
            running[0] -= 1
            return 0

    async def go():
        return await asyncio.gather(api.find_proxies_async(), api.find_proxies_async(verbose=True),
                                    api.find_proxies_async())

    monkeypatch.setattr(app, "Run", Slow)
    original = widgets.console
    assert all(len(r) == 4 for r in asyncio.run(go()))
    assert most[0] == 1 and widgets.console is original
    assert capsys.readouterr().out.count("niemand") == 1  # nur der Aufruf mit verbose=True


def test_waiting_call_can_be_cancelled():
    async def go():
        with api._RUN_LOCK:
            waiter = asyncio.ensure_future(api.find_proxies_async())
            await asyncio.sleep(0.1)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        assert api._RUN_LOCK.acquire(blocking=False)  # keine hängende Sperre
        api._RUN_LOCK.release()

    asyncio.run(go())


def test_runs_in_the_same_second_get_their_own_folder(tmp_path):
    from proxyscraper.output import new_run_dir
    first, second = new_run_dir(tmp_path), new_run_dir(tmp_path)
    assert first != second and first.is_dir() and second.is_dir()
