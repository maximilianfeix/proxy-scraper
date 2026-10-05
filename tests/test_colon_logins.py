"""Logins written as ip:port:user:pass, the way paid proxy lists often export them (#254)."""

import pytest

from proxyscraper import app
from proxyscraper import parsing as p
from proxyscraper.history import ProxyHistory

from .test_recheck_stdin import FakeStdin


@pytest.mark.parametrize("line,default,key", [
    ("8.8.4.4:8080:alice:s3cret", "http", "http alice:s3cret@8.8.4.4:8080"),
    ("socks5://8.8.4.4:1080:alice:s3cret", None, "socks5 alice:s3cret@8.8.4.4:1080"),
    ("8.8.4.4:8080:alice:p@ss", "http", "http alice:p%40ss@8.8.4.4:8080"),
    ("8.8.4.4:8080:alice:s3cret  # office", "http", "http alice:s3cret@8.8.4.4:8080"),
])
def test_a_line_reads_the_login_after_the_port(line, default, key):
    assert p.parse_proxy_line(line, default) == key


@pytest.mark.parametrize("line", [
    "8.8.4.4:8080:alice",           # three parts: no password, not a login
    "8.8.4.4:8080:alice:s3cret:x",  # five parts: not this format
    "8.8.4.4:8080::s3cret",         # no user
    "8.8.4.4:99999:alice:s3cret",   # not a port
    "2001:db8::1:8080",             # IPv6 isn't read at all
])
def test_other_shapes_are_not_logins(line):
    key = p.parse_proxy_line(line, "http")
    assert key is None or "@" not in key


def test_the_usual_form_still_wins():
    assert p.parse_proxy_line("alice:s3cret@8.8.4.4:8080", "http") == "http alice:s3cret@8.8.4.4:8080"


def test_a_file_of_colon_logins(tmp_path):
    f = tmp_path / "http-paid.txt"  # the type comes from the file name, as for ip:port lines
    f.write_text("8.8.4.4:8080:alice:s3cret\n9.9.9.10:3128:bob:hunter2\n", encoding="utf-8")
    jobs = app.load_recheck_jobs(str(f), ("http",), ProxyHistory(tmp_path / "h.json"))
    assert jobs == ["http alice:s3cret@8.8.4.4:8080", "http bob:hunter2@9.9.9.10:3128"]


def test_stdin_keeps_the_login_and_the_bare_address(monkeypatch, tmp_path):
    """A list like ip:port:US:elite has the same shape – the address on its own is tried too, so such a
    proxy isn't lost to a login that never was."""
    monkeypatch.setattr("sys.stdin", FakeStdin("8.8.4.4:8080:alice:s3cret\n"))
    jobs = app.load_recheck_jobs("-", ("http", "socks5"), ProxyHistory(tmp_path / "h.json"))
    assert set(jobs) == {"http alice:s3cret@8.8.4.4:8080", "socks5 alice:s3cret@8.8.4.4:8080",
                         "http 8.8.4.4:8080", "socks5 8.8.4.4:8080"}
    assert jobs[0] == "http alice:s3cret@8.8.4.4:8080"  # the login first: it's what the line most likely means


def test_sources_read_colon_logins_next_to_the_bare_address():
    found = p.validate_candidates(p.extract_candidates(b"8.8.4.4:8080:alice:s3cret\n1.2.3.4:80\n", "http"))
    assert found == {"http alice:s3cret@8.8.4.4:8080", "http 8.8.4.4:8080", "http 1.2.3.4:80"}


def test_the_parser_version_moves_on():
    assert p.PARSER_VERSION >= 4  # cached sources have to be read again
