"""Blocklist lookup of exit IPs (SpamCop): probe, answers, cache, filter and what gets published."""

import asyncio

from proxyscraper import publish
from proxyscraper.blocklist import Blocklist, query_name
from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.options import Filters, RunOptions
from proxyscraper.output import ResultWriter

LISTED = {"1.1.1.1", "127.0.0.2"}


def resolver(answers=None, calls=None):
    """Like a DNS resolver in front of SpamCop: listed IPs resolve to 127.0.0.2, others don't resolve."""
    async def resolve(name):
        if calls is not None:
            calls.append(name)
        ip = ".".join(reversed(name.split(".")[:4]))
        if answers is not None:
            return answers
        return "127.0.0.2" if ip in LISTED else None
    return resolve


def test_query_name():
    assert query_name("1.2.3.4") == "4.3.2.1.bl.spamcop.net"
    assert query_name("2001:db8::1") is None and query_name("1.2.3") is None and query_name("1.2.3.999") is None


def test_listed_unlisted_and_cached():
    calls = []

    async def go():
        bl = Blocklist(resolver(calls=calls))
        assert await bl.probe()
        results = [await bl.lookup("1.1.1.1"), await bl.lookup("8.8.8.8"), await bl.lookup("1.1.1.1")]
        return results, bl.listed

    results, listed = asyncio.run(go())
    assert results == [True, False, True] and listed == 1
    assert calls.count("1.1.1.1.bl.spamcop.net") == 1  # cached for the run


def test_a_refusing_resolver_makes_everything_unknown():
    async def go():
        bl = Blocklist(resolver(answers="127.255.255.254"))  # "public resolver, query refused"
        usable = await bl.probe()
        return usable, await bl.lookup("1.1.1.1")

    assert asyncio.run(go()) == (False, None)


def test_a_resolver_that_lists_everything_is_not_trusted():
    async def go():
        bl = Blocklist(resolver(answers="127.0.0.2"))  # even 127.0.0.1 "listed" – something's off
        return await bl.probe()

    assert asyncio.run(go()) is False


def test_filter_drops_listed_but_keeps_unknown():
    f = Filters(no_blocklisted=True)
    listed = CheckResult("http 1.1.1.1:80", "http", "1.1.1.1:80", 100, "1.1.1.1", blocklisted=True)
    clean = CheckResult("http 2.2.2.2:80", "http", "2.2.2.2:80", 100, "2.2.2.2", blocklisted=False)
    unknown = CheckResult("http 3.3.3.3:80", "http", "3.3.3.3:80", 100, "3.3.3.3")
    assert [f.accepts(r) for r in (listed, clean, unknown)] == [False, True, True]
    assert not f.may_pass(listed) and f.active and "not blocklisted" in f.describe()


def test_options_roundtrip():
    opts = RunOptions.from_args(parse_args(["--no-blocklisted", "--no-dnsbl"]))
    assert opts.filters.no_blocklisted and opts.no_dnsbl
    assert RunOptions.from_args(parse_args(opts.to_argv())) == opts


def test_published_stats_only_count_when_the_lookup_ran(tmp_path):
    def run(blocklisted):
        rows = [CheckResult(f"http 1.1.1.{i}:80", "http", f"1.1.1.{i}:80", 100, "9.9.9.9", True, "elite", "DE",
                            blocklisted=b) for i, b in enumerate(blocklisted)]
        run_dir = tmp_path / f"run{len(list(tmp_path.iterdir()))}"
        ResultWriter(run_dir=run_dir).finalize(rows)
        return publish.stats_for(publish.load_rows(run_dir), publish.datetime.now(publish.timezone.utc))

    assert run([True, False, True])["blocklisted"] == 2
    assert run([None, None, None])["blocklisted"] is None  # not "none listed", just unknown
