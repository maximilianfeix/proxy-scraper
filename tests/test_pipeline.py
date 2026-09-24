import json

from proxyscraper import output, pipeline
from proxyscraper import sources as srcs
from proxyscraper.checker import CheckResult
from proxyscraper.geo import flag
from proxyscraper.history import MAX_FAIL_STREAK, ProxyHistory
from proxyscraper.ui import bar, fmt, pct


def result(key="http 1.1.1.1:80", latency=500, https=True, anonymity="elite", country="DE"):
    ptype, proxy = key.split(" ")
    return CheckResult(key, ptype, proxy, latency, "9.9.9.9", https, anonymity, country)


def test_attribute_results_counts_per_source():
    res = pipeline.ScrapeResult(["a", "b"], {"http 1.1.1.1:80": [0, 1], "http 2.2.2.2:80": [1]})
    out = pipeline.attribute_results(res, ["http 1.1.1.1:80", "http 2.2.2.2:80"], {"http 1.1.1.1:80"})
    assert out == {"a": (1, 1), "b": (2, 1)}


def test_prioritize_history_first_then_good_sources(tmp_path):
    quality = srcs.SourceStats(tmp_path / "stats.json")
    quality.record_checks({"good": (100, 50), "bad": (100, 0)})
    history = ProxyHistory(tmp_path / "h.json")
    history.record_ok("socks5 7.7.7.7:1080", 100, "7.7.7.7")
    history.record_ok("socks4 8.8.8.8:1080", 100, "8.8.8.8")  # Typ nicht gewünscht
    res = pipeline.ScrapeResult(["bad", "good"], {"http 1.1.1.1:80": [0], "http 2.2.2.2:80": [1]})
    order = pipeline.prioritize(res, quality, history, ["http", "socks5"])
    assert order == ["socks5 7.7.7.7:1080", "http 2.2.2.2:80", "http 1.1.1.1:80"]


def test_best_sources_needs_minimum_sample():
    per = {"a": (100, 10), "b": (10, 5), "c": (50, 0)}
    assert [u for *_, u in pipeline.best_sources(per)] == ["a"]


def test_history_reliability_and_pruning(tmp_path):
    h = ProxyHistory(tmp_path / "h.json")
    h.record_ok("http 1.1.1.1:80", 300, "1.1.1.1", now=1000.0, country="DE", https=True)
    h.record_ok("http 2.2.2.2:80", 300, "2.2.2.2", now=1000.0)
    for _ in range(MAX_FAIL_STREAK):
        h.record_fail("http 2.2.2.2:80")
    h.record_fail("http 3.3.3.3:80")  # unbekannt -> wird nicht angelegt
    assert h.ranked_keys()[0] == "http 1.1.1.1:80"
    assert h.prune(now=1001.0) == 1
    h.save()
    again = ProxyHistory(tmp_path / "h.json")
    assert list(again.records) == ["http 1.1.1.1:80"]
    assert again.get("http 1.1.1.1:80").country == "DE"


def test_filters():
    f = output.Filters(countries={"DE"}, https_only=True, min_anonymity="anonymous", max_latency=1000)
    assert f.accepts(result())
    assert not f.accepts(result(country="US"))
    assert not f.accepts(result(https=False))
    assert not f.accepts(result(anonymity="transparent"))
    assert not f.accepts(result(latency=1500))
    assert f.needs_details and f.active
    assert not output.Filters().active


def test_result_writer_creates_all_formats(tmp_path):
    w = output.ResultWriter(run_dir=tmp_path / "run1", extra_file=tmp_path / "extra.txt")
    rows = [result("socks5 2.2.2.2:1080", 900), result("http 1.1.1.1:80", 200)]
    w.add_live(rows[0])
    files = w.finalize(rows)
    run = tmp_path / "run1"
    assert (run / "all.txt").read_text() == "http://1.1.1.1:80\nsocks5://2.2.2.2:1080\n"
    assert (run / "socks5.txt").read_text() == "2.2.2.2:1080\n"
    assert json.loads((run / "proxies.json").read_text())[0]["url"] == "http://1.1.1.1:80"
    assert (run / "proxies.csv").read_text().splitlines()[0].startswith("ptype,proxy,latency")
    assert (tmp_path / "extra.txt").exists()
    assert len(files) == 6  # all, http, socks5, json, csv, -o
    assert output.latest_run_dir(tmp_path) == run
    assert output.latest_results(tmp_path) == ["http://1.1.1.1:80", "socks5://2.2.2.2:1080"]


def test_latest_pointer_works_without_symlinks(tmp_path, monkeypatch):
    def no_symlinks(*args, **kwargs):
        raise OSError("symbolic links not permitted")  # Windows ohne Admin-/Entwicklerrechte

    monkeypatch.setattr(output.os, "symlink", no_symlinks)
    for name in ("run1", "run2"):
        w = output.ResultWriter(run_dir=tmp_path / name)
        w.finalize([result(f"http 1.1.1.{len(name)}:80")])
    assert not (tmp_path / "latest").exists()
    assert output.latest_run_dir(tmp_path) == tmp_path / "run2"


def test_latest_results_empty_without_runs(tmp_path):
    assert output.latest_run_dir(tmp_path) is None
    assert output.latest_results(tmp_path) == []


def test_ui_helpers():
    assert fmt(1234567) == "1.234.567"
    assert pct(1, 3) == "33,3 %" and pct(1, 0) == "–"
    assert bar(5, 10, 4, "green").plain == "██··"
    assert flag("DE") == "🇩🇪" and flag("") == "  "
