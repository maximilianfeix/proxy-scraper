"""Small robustness fixes from the package review (#84)."""

import asyncio
import json

from proxyscraper import app, pipeline
from proxyscraper import sources as srcs
from proxyscraper.checker import classify_anonymity
from proxyscraper.history import ProxyHistory
from proxyscraper.options import RunOptions
from proxyscraper.parsing import parse_proxy_line


def test_scheme_without_address_is_skipped():
    for line in ("http://", "socks5://   ", "socks4://\t"):
        assert parse_proxy_line(line) is None
    assert parse_proxy_line("socks5://1.2.3.4:1080 # comment") == "socks5 1.2.3.4:1080"


def test_own_ip_must_match_as_a_whole_address():
    body = json.dumps({"origin": "11.2.3.45", "headers": {"Host": "httpbin.org"}}).encode()
    assert classify_anonymity(body, ["1.2.3.4"]) == "elite"
    leaked = json.dumps({"origin": "11.2.3.45", "headers": {"X-Forwarded-For": "1.2.3.4"}}).encode()
    assert classify_anonymity(leaked, ["1.2.3.4"]) == "transparent"
    assert classify_anonymity(b'{"origin": "1.2.3.4, 5.6.7.8", "headers": {}}', ["1.2.3.4"]) == "transparent"


def test_missing_recheck_file_is_a_message_not_a_traceback(tmp_path, monkeypatch):
    notes = []
    monkeypatch.setattr(app, "note", lambda text, *a: notes.append(text))
    monkeypatch.setattr(app, "info", lambda *a, **k: None)
    run = app.Run(RunOptions(recheck=str(tmp_path / "typo.txt")), show_banner=False)
    run.history = ProxyHistory(tmp_path / "history.json")
    assert asyncio.run(run.gather_jobs()) == []
    assert any("typo.txt" in n for n in notes)


def test_gh_is_only_asked_when_discovery_can_run(monkeypatch):
    calls = []
    monkeypatch.setattr(srcs, "github_token", lambda: calls.append(1) or "t")
    monkeypatch.setattr(srcs, "discovered_age_days", lambda: 0.5)  # searched recently
    monkeypatch.setattr(srcs, "load_source_file", lambda: ({}, []))
    monkeypatch.setattr(srcs, "load_discovered", dict)

    async def no_meta(meta, get):
        return {}, 0
    monkeypatch.setattr(srcs, "resolve_meta", no_meta)
    asyncio.run(pipeline.collect_sources(RunOptions(), srcs.SourceStats()))
    assert calls == []
