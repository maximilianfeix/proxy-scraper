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


def test_a_url_elsewhere_on_the_line_doesnt_hide_the_proxy(monkeypatch, tmp_path):
    """One-line API JSON with a URL field, or a note with a link – the proxy on that line still counts."""
    text = ('[{"ip": "8.8.4.4", "port": "3128", "source": "https://example.com/list"}]\n'
            "1.0.0.4:8080  # via https://example.com\n")
    monkeypatch.setattr("sys.stdin", FakeStdin(text))
    jobs = set(app.load_recheck_jobs("-", ("http",), ProxyHistory(tmp_path / "h.json")))
    assert jobs == {"http 8.8.4.4:3128", "http 1.0.0.4:8080"}


def test_a_big_mixed_paste_stays_fast(monkeypatch, tmp_path):
    import time
    typed = "".join(f"socks5://9.9.{i // 250}.{i % 250 + 1}:1080\n" for i in range(20_000))
    bare = "".join(f"8.8.{i // 250}.{i % 250 + 1}:8080\n" for i in range(20_000))
    monkeypatch.setattr("sys.stdin", FakeStdin(typed + bare))
    started = time.perf_counter()
    jobs = app.load_recheck_jobs("-", ("http", "socks5"), ProxyHistory(tmp_path / "h.json"))
    assert len(jobs) == 60_000 and time.perf_counter() - started < 5


def test_bare_lines_count_whatever_else_is_in_the_paste(monkeypatch, tmp_path):
    """Found in review: a rejected typed line (private IP) or one with the scheme mid-line made the bare
    lines lose the source "majority" vote and vanish."""
    for text, expected in [
        ("socks5://10.0.0.1:1080\n8.8.4.4:8080\n", {"http 8.8.4.4:8080", "socks5 8.8.4.4:8080"}),
        ("proxy: socks5://9.9.9.10:1080\n8.8.4.4:8080\n",
         {"socks5 9.9.9.10:1080", "http 8.8.4.4:8080", "socks5 8.8.4.4:8080"}),
    ]:
        monkeypatch.setattr("sys.stdin", FakeStdin(text))
        assert set(app.load_recheck_jobs("-", ("http", "socks5"), ProxyHistory(tmp_path / "h.json"))) == expected
