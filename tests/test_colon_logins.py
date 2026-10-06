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
    ("http://8.8.4.4:8080:alice:s3cret/", None, "http alice:s3cret@8.8.4.4:8080"),  # like ip:port/
])
def test_a_line_reads_the_login_after_the_port(line, default, key):
    assert p.parse_proxy_line(line, default) == key


@pytest.mark.parametrize("line", [
    "8.8.4.4:8080:alice",           # three parts: no password, not a login
    "8.8.4.4:8080:alice:s3cret:x",  # five parts: not this format
    "8.8.4.4:8080::s3cret",         # no user
    "8.8.4.4:99999:alice:s3cret",   # not a port
    "2001:db8::1:8080",             # IPv6 isn't read at all
    "8.8.4.4:8080:alice:s3cret,US", # a CSV row: the line is no proxy as a whole
])
def test_other_shapes_are_not_logins(line):
    assert p.parse_proxy_line(line, "http") is None


def test_the_usual_form_still_wins():
    assert p.parse_proxy_line("alice:s3cret@8.8.4.4:8080", "http") == "http alice:s3cret@8.8.4.4:8080"


def test_a_file_of_colon_logins(tmp_path):
    f = tmp_path / "http-paid.txt"  # the type comes from the file name, as for ip:port lines
    f.write_text("8.8.4.4:8080:alice:s3cret\n9.9.9.10:3128:bob:hunter2\n", encoding="utf-8")
    jobs = app.load_recheck_jobs(str(f), ("http",), ProxyHistory(tmp_path / "h.json"))
    # the bare address after each login: "ip:port:US:elite" lists look the same
    assert jobs == ["http alice:s3cret@8.8.4.4:8080", "http 8.8.4.4:8080",
                    "http bob:hunter2@9.9.9.10:3128", "http 9.9.9.10:3128"]


def test_stdin_keeps_the_login_and_the_bare_address(monkeypatch, tmp_path):
    """A list like ip:port:US:elite has the same shape – the address on its own is tried too, so such a
    proxy isn't lost to a login that never was."""
    monkeypatch.setattr("sys.stdin", FakeStdin("8.8.4.4:8080:alice:s3cret\n"))
    jobs = app.load_recheck_jobs("-", ("http", "socks5"), ProxyHistory(tmp_path / "h.json"))
    assert set(jobs) == {"http alice:s3cret@8.8.4.4:8080", "socks5 alice:s3cret@8.8.4.4:8080",
                         "http 8.8.4.4:8080", "socks5 8.8.4.4:8080"}
    assert jobs[0] == "http alice:s3cret@8.8.4.4:8080"  # the login first: it's what the line most likely means


def test_stdin_keeps_the_bare_address_when_the_password_has_an_at():
    keys = app.stdin_keys(b"8.8.4.4:8080:alice:p@ss\n", ("http",))
    assert keys == ["http alice:p%40ss@8.8.4.4:8080", "http 8.8.4.4:8080"]


def test_a_typed_colon_login_keeps_the_bare_address_too():
    keys = app.stdin_keys(b"socks5://8.8.4.4:1080:US:elite\n", ("socks5",))
    assert keys == ["socks5 US:elite@8.8.4.4:1080", "socks5 8.8.4.4:1080"]


@pytest.mark.parametrize("paste", [
    b"8.8.4.4:8080:alice:s3cret,US,elite\n",
    b'{"proxy":"8.8.4.4:8080:alice:s3cret","x":1}',
    b"8.8.4.4:8080:alice:s3cret;x\n",
    b"| 8.8.4.4:8080:alice:s3cret | US |\n",
])
def test_the_password_ends_where_the_paste_punctuation_starts(paste):
    keys = app.stdin_keys(paste, ("http",))
    assert keys == ["http alice:s3cret@8.8.4.4:8080", "http 8.8.4.4:8080"]


@pytest.mark.parametrize("data", [
    b"8.8.4.4:8080:US:elite\n1.2.3.4:80\n",
    b"socks5://8.8.4.4:1080:alice:s3cret\n",
    b"8.8.4.4:8080:alice:s3cret,US\n",
])
def test_scraped_sources_never_make_up_logins(data):
    found = p.validate_candidates(p.extract_candidates(data, "auto"))
    assert not any("@" in k for k in found), found
