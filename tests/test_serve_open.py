"""--serve-host outside 127.0.0.1 without a password is an open proxy: it only starts with --serve-open."""

import asyncio

import pytest

from proxyscraper import app, cli
from proxyscraper.cli import parse_args
from proxyscraper.options import RunOptions


@pytest.fixture(autouse=True)
def no_password_from_env(monkeypatch):
    monkeypatch.delenv("PROXY_SCRAPER_SERVE_PASSWORD", raising=False)


def opts(*argv):
    return RunOptions.from_args(parse_args(list(argv)))


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "example.org"])
def test_open_server_is_refused(host):
    refusal = app.open_server_refusal(opts("--serve", "--serve-host", host))
    assert refusal and host in refusal and "PROXY_SCRAPER_SERVE_PASSWORD" in refusal and "--serve-open" in refusal


@pytest.mark.parametrize("argv", [
    ["--serve"],                                               # 127.0.0.1
    ["--serve", "--serve-host", "::1"],
    ["--serve", "--serve-host", "localhost"],
    ["--serve", "--serve-host", "0.0.0.0", "--serve-password", "s3cret"],
    ["--serve", "--serve-host", "0.0.0.0", "--serve-open"],    # the deliberate opt-in
    ["--serve-host", "0.0.0.0"],                               # no server at all
])
def test_allowed_settings(argv):
    assert app.open_server_refusal(opts(*argv)) is None


def test_password_from_the_environment_counts(monkeypatch):
    monkeypatch.setenv("PROXY_SCRAPER_SERVE_PASSWORD", "from-env")
    assert app.open_server_refusal(opts("--serve", "--serve-host", "0.0.0.0")) is None


def test_serve_open_survives_the_argv_roundtrip():
    o = opts("--serve", "--serve-host", "0.0.0.0", "--serve-open")
    assert o.serve_open and "--serve-open" in o.to_argv()
    assert RunOptions.from_args(parse_args(o.to_argv())) == o
    assert "--serve-open" not in opts("--serve").to_argv()


def test_cli_refuses_before_the_scan(monkeypatch):
    async def must_not_run(self):
        raise AssertionError("the scan started although the server would have been refused")

    monkeypatch.setattr(app.Run, "execute", must_not_run)
    assert cli.run(["--recheck", "--serve", "--serve-host", "0.0.0.0"]) == 2


def test_run_serve_refuses_without_listening(monkeypatch):
    """Run used on its own (without cli.run) refuses as well – nothing ever listens."""
    async def must_not_listen(self):
        raise AssertionError("the open server started listening")

    monkeypatch.setattr(app.RotatingServer, "start", must_not_listen)
    run = app.Run.__new__(app.Run)
    run.opts = opts("--serve", "--serve-host", "0.0.0.0")
    asyncio.run(asyncio.wait_for(run.serve([_result()]), 5))


def _result():
    from proxyscraper.checker import CheckResult
    return CheckResult("http 1.2.3.4:80", "http", "1.2.3.4:80", 100, "1.2.3.4")
