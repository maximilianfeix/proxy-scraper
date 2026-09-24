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
    ["--recheck", "meine liste.txt", "--limit", "200", "--timeout", "5.5"],
    ["--concurrency", "500", "--connect-timeout", "2", "--no-discover", "--all-sources", "-o", "out.txt"],
])
def test_argv_roundtrip(argv):
    opts = RunOptions.from_args(parse_args(argv))
    assert RunOptions.from_args(parse_args(opts.to_argv())) == opts


def test_types_are_normalized():
    assert RunOptions(types=["socks5", "http", "http"]).types == ["http", "socks5"]
    assert RunOptions.from_args(parse_args(["--types", "socks5", "socks4", "http"])) == RunOptions()


def test_to_command_quotes_arguments():
    opts = RunOptions(recheck="meine liste.txt", types=["socks5"])
    assert opts.to_command() == "python3 proxy_scraper.py --types socks5 --recheck 'meine liste.txt'"


def test_details_and_geo_are_forced_by_filters():
    assert not RunOptions(fast=True).details
    assert RunOptions(fast=True, filters=Filters(https_only=True)).details
    assert not RunOptions(no_geo=True).geo
    assert RunOptions(no_geo=True, filters=Filters(countries={"DE"})).geo
