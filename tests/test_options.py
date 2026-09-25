import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.options import Filters, RunOptions, parse_countries


def result(latency=500, https=True, anonymity="elite", country="DE"):
    return CheckResult("http 1.1.1.1:80", "http", "1.1.1.1:80", latency, "9.9.9.9", https, anonymity, country)


def test_filters():
    f = Filters(countries={"DE"}, https_only=True, min_anonymity="anonymous", max_latency=1000)
    assert f.accepts(result())
    assert not f.accepts(result(country="US"))
    assert not f.accepts(result(https=False))
    assert not f.accepts(result(anonymity="transparent"))
    assert not f.accepts(result(latency=1500))
    assert f.needs_details and f.active
    assert not Filters().active


def test_parse_countries():
    assert parse_countries(" de, at,,CH ") == {"DE", "AT", "CH"}
    assert parse_countries(None) == set()


def test_defaults_match_argparse():
    assert RunOptions.from_args(parse_args([])) == RunOptions()
    assert RunOptions().to_argv() == []


@pytest.mark.parametrize("argv", [
    ["--types", "socks5"],
    ["--types", "socks5", "socks4", "http"],
    ["--types", "socks5", "http", "http"],
    ["--types", "http", "socks5", "--country", "AT,DE", "--https-only", "--want", "50"],
    ["--anonymity", "elite", "--max-latency", "1500", "--fast", "--no-geo"],
    ["--recheck"],
    ["--recheck", "my list.txt", "--limit", "200", "--timeout", "5.5"],
    ["--concurrency", "500", "--connect-timeout", "2", "--no-discover", "--all-sources", "-o", "out.txt"],
    ["--recheck", "--serve"],
    ["--serve", "9000"],
    ["--export", "clash,proxychains"],
    ["--export", "all", "-o", "x.txt"],
])
def test_argv_roundtrip(argv):
    opts = RunOptions.from_args(parse_args(argv))
    assert RunOptions.from_args(parse_args(opts.to_argv())) == opts


def test_types_are_normalized():
    assert RunOptions(types=["socks5", "http", "http"]).types == ["http", "socks5"]
    assert RunOptions.from_args(parse_args(["--types", "socks5", "socks4", "http"])) == RunOptions()


@pytest.mark.parametrize("types", [[], ["ftp"], ["http", "socks6"]])
def test_invalid_types_are_rejected(types):
    with pytest.raises(ValueError):
        RunOptions(types=types)


@pytest.mark.parametrize("argv", [
    ["-c", "0"], ["--timeout", "0"], ["--connect-timeout", "-1"], ["--want", "-5"],
    ["--limit", "x"], ["--max-latency", "-100"], ["--list-sources", "0"], ["--serve", "0"], ["--serve", "70000"],
])
def test_invalid_numbers_are_rejected_by_argparse(argv, capsys):
    with pytest.raises(SystemExit):
        parse_args(argv)
    err = capsys.readouterr().err
    assert "must be" in err or "not a number" in err


@pytest.mark.parametrize("changes", [
    {"concurrency": 0}, {"timeout": 0}, {"connect_timeout": -1}, {"want": -1},
    {"filters": Filters(max_latency=-1)},
])
def test_invalid_numbers_are_rejected_by_run_options(changes):
    with pytest.raises(ValueError):
        RunOptions(**changes)


def test_to_command_quotes_arguments():
    opts = RunOptions(recheck="my list.txt", types=["socks5"])
    assert opts.to_command() == "python3 proxy_scraper.py --types socks5 --recheck 'my list.txt'"


def test_details_and_geo_are_forced_by_filters():
    assert not RunOptions(fast=True).details
    assert RunOptions(fast=True, filters=Filters(https_only=True)).details
    assert not RunOptions(no_geo=True).geo
    assert RunOptions(no_geo=True, filters=Filters(countries={"DE"})).geo


def test_check_timeout_follows_latency_limit():
    opts = RunOptions(timeout=8, connect_timeout=4, filters=Filters(max_latency=1500))
    assert (opts.check_timeout, opts.check_connect_timeout) == (1.5, 1.5)
    assert RunOptions(timeout=8, filters=Filters(max_latency=20000)).check_timeout == 8  # limit above the timeout
    assert (RunOptions().check_timeout, RunOptions().check_connect_timeout) == (8.0, 4.0)


@pytest.mark.parametrize("filters, r, expected", [
    (Filters(min_anonymity="elite"), result(anonymity="anonymous"), False),
    (Filters(min_anonymity="anonymous"), result(anonymity="elite"), True),
    (Filters(countries={"AT"}), result(country="DE"), False),
    (Filters(countries={"AT"}), result(country=""), True),       # country still unknown -> could match
    (Filters(https_only=True), result(https=None), True),         # HTTPS is only checked later
    (Filters(max_latency=400), result(latency=500), False),
])
def test_may_pass(filters, r, expected):
    assert filters.may_pass(r) == expected


def test_serve_defaults():
    assert parse_args(["--serve"]).serve == 8899
    assert parse_args([]).serve == 0
    assert RunOptions(serve=8899).to_argv() == ["--serve"]
    assert RunOptions(serve=9000).to_argv() == ["--serve", "9000"]
    with pytest.raises(ValueError):
        RunOptions(serve=70000)
