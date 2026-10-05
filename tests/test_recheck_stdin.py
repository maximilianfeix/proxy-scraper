"""--recheck - reads the candidates from stdin (#248)."""

import asyncio
import io

from proxyscraper import app
from proxyscraper.history import ProxyHistory
from proxyscraper.options import RunOptions


class FakeStdin(io.StringIO):
    def __init__(self, text, tty=False):
        super().__init__(text)
        self.tty = tty

    def isatty(self):
        return self.tty


def test_reads_the_candidates_from_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", FakeStdin("socks5://9.9.9.10:1080\n8.8.4.4:8080\nnot a proxy\n"))
    jobs = app.load_recheck_jobs("-", ("http", "socks5"), ProxyHistory(tmp_path / "h.json"))
    # a bare ip:port has no type, so it's tried as HTTP and SOCKS5 like in any untyped list
    assert jobs[0] == "socks5 9.9.9.10:1080"
    assert "http 8.8.4.4:8080" in jobs and "socks5 8.8.4.4:8080" in jobs
    assert len(jobs) == 3


def test_keeps_only_the_wanted_types(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", FakeStdin("socks4://1.0.0.4:4145\nhttp://8.8.4.4:8080\n"))
    assert app.load_recheck_jobs("-", ("http",), ProxyHistory(tmp_path / "h.json")) == ["http 8.8.4.4:8080"]


def test_logins_survive(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", FakeStdin("socks5://alice:secret@9.9.9.10:1080\n"))
    assert app.load_recheck_jobs("-", ("socks5",), ProxyHistory(tmp_path / "h.json")) == [
        "socks5 alice:secret@9.9.9.10:1080"]


def test_a_terminal_on_stdin_is_a_clear_message(monkeypatch, tmp_path):
    """Nothing piped in: stdin is the terminal, and reading it would just wait forever."""
    monkeypatch.setattr("sys.stdin", FakeStdin("", tty=True))
    notes = []
    monkeypatch.setattr(app, "note", lambda text, *a: notes.append(text))
    monkeypatch.setattr(app, "info", lambda *a, **k: None)
    run = app.Run(RunOptions(recheck="-"), show_banner=False)
    run.history = ProxyHistory(tmp_path / "history.json")
    assert asyncio.run(run.gather_jobs()) == []
    assert any("nothing was piped in" in n and "--recheck -" in n for n in notes)


def test_the_summary_line_says_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", FakeStdin("socks5://9.9.9.10:1080\n"))
    shown = []
    monkeypatch.setattr(app, "info", lambda label, text, *a, **k: shown.append(text))
    run = app.Run(RunOptions(recheck="-"), show_banner=False)
    run.history = ProxyHistory(tmp_path / "history.json")
    asyncio.run(run.gather_jobs())
    assert any("from stdin" in s for s in shown)


def test_finds_proxies_in_any_text(monkeypatch, tmp_path):
    """JSON or a table pasted from a website works too – the same extraction as for sources."""
    monkeypatch.setattr("sys.stdin", FakeStdin('[{"ip": "8.8.4.4", "port": "3128"}]'))
    assert set(app.load_recheck_jobs("-", ("http",), ProxyHistory(tmp_path / "h.json"))) == {"http 8.8.4.4:3128"}


def test_private_and_documentation_addresses_are_left_out(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", FakeStdin("192.168.1.10:8080\nsocks5://203.0.113.10:1080\n"))
    assert app.load_recheck_jobs("-", ("http", "socks5"), ProxyHistory(tmp_path / "h.json")) == []
