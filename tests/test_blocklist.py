"""Blocklist lookup of exit IPs (SpamCop): probe, answers, cache, filter and what gets published."""

import asyncio

import pytest

from proxyscraper import publish
from proxyscraper.blocklist import NOT_LISTED, Blocklist, query_name
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
        return "127.0.0.2" if ip in LISTED else NOT_LISTED
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


def test_dns_errors_and_timeouts_stay_unknown(monkeypatch):
    import proxyscraper.blocklist as bl_module
    monkeypatch.setattr(bl_module, "LOOKUP_TIMEOUT", 0.05)

    async def flaky(name):
        ip = ".".join(reversed(name.split(".")[:4]))
        if ip == "127.0.0.2":
            return "127.0.0.2"
        if ip == "127.0.0.1":
            return NOT_LISTED
        if ip == "5.5.5.5":
            await asyncio.sleep(1)  # the resolver hangs
        return None  # SERVFAIL and friends

    async def go():
        bl = Blocklist(flaky)
        assert await bl.probe()
        return await bl.lookup("4.4.4.4"), await bl.lookup("5.5.5.5")

    assert asyncio.run(go()) == (None, None)  # unknown, never "not listed"


def test_system_resolver_tells_nxdomain_from_errors(monkeypatch):
    import socket

    import proxyscraper.blocklist as bl_module
    monkeypatch.undo()  # the autouse fixture replaced system_resolve – this test is about the real one

    def fake(errno):
        async def getaddrinfo(*a, **k):
            raise socket.gaierror(errno, "x")
        return getaddrinfo

    async def go(errno):
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "getaddrinfo", fake(errno))
        return await bl_module.system_resolve("4.4.4.4.bl.spamcop.net")

    assert asyncio.run(go(socket.EAI_NONAME)) == NOT_LISTED
    assert asyncio.run(go(socket.EAI_AGAIN)) is None


# --------------------------------------------------------------------------- #
# parallel lookups of the same exit IP share one resolver call
# --------------------------------------------------------------------------- #

def gated_resolver(calls, gate, fail=None):
    """Answers like `resolver`, but every lookup of a proxy IP waits for `gate` – so callers really overlap.
    fail: IPs whose lookup raises."""
    async def resolve(name):
        ip = ".".join(reversed(name.split(".")[:4]))
        if ip.startswith("127.0.0."):  # the probe
            return "127.0.0.2" if ip == "127.0.0.2" else NOT_LISTED
        calls.append(ip)
        await gate.wait()
        if fail and ip in fail:
            raise RuntimeError("resolver broke")
        return "127.0.0.2" if ip in LISTED else NOT_LISTED
    return resolve


def test_parallel_lookups_of_one_ip_share_one_query():
    calls = []

    async def go():
        gate = asyncio.Event()
        bl = Blocklist(gated_resolver(calls, gate))
        assert await bl.probe()
        waiting = [asyncio.ensure_future(bl.lookup("1.1.1.1")) for _ in range(100)]
        waiting += [asyncio.ensure_future(bl.lookup("8.8.8.8")) for _ in range(50)]
        await asyncio.sleep(0.01)
        gate.set()
        results = await asyncio.gather(*waiting)
        return results, bl

    results, bl = asyncio.run(go())
    assert sorted(calls) == ["1.1.1.1", "8.8.8.8"]  # one query per IP, not one per caller
    assert results == [True] * 100 + [False] * 50
    assert bl.listed == 1  # counted once, not per caller
    assert not bl._inflight


def test_a_failing_shared_lookup_reaches_every_caller_and_is_retried_later():
    calls = []

    async def go():
        gate = asyncio.Event()
        bl = Blocklist(gated_resolver(calls, gate, fail={"1.1.1.1"}))
        assert await bl.probe()
        waiting = [asyncio.ensure_future(bl.lookup("1.1.1.1")) for _ in range(10)]
        await asyncio.sleep(0.01)
        gate.set()
        results = await asyncio.gather(*waiting, return_exceptions=True)
        assert not bl._inflight and "1.1.1.1" not in bl._cache  # an error isn't cached, no entry hangs
        with pytest.raises(RuntimeError):
            await bl.lookup("1.1.1.1")
        return results

    results = asyncio.run(go())
    assert all(isinstance(r, RuntimeError) for r in results)
    assert calls == ["1.1.1.1", "1.1.1.1"]  # one shared query, then one fresh retry


def test_one_caller_cancelling_doesnt_cancel_the_lookup_for_the_others():
    calls = []

    async def go():
        gate = asyncio.Event()
        bl = Blocklist(gated_resolver(calls, gate))
        assert await bl.probe()
        first = asyncio.ensure_future(bl.lookup("1.1.1.1"))
        second = asyncio.ensure_future(bl.lookup("1.1.1.1"))
        await asyncio.sleep(0.01)
        first.cancel()
        await asyncio.sleep(0)
        gate.set()
        result = await second
        assert first.cancelled()
        return result, bl

    result, bl = asyncio.run(go())
    assert result is True and calls == ["1.1.1.1"]
    assert bl._cache == {"1.1.1.1": True} and not bl._inflight


def test_a_lookup_every_caller_abandoned_still_finishes_and_cleans_up():
    calls = []

    async def go():
        gate = asyncio.Event()
        bl = Blocklist(gated_resolver(calls, gate))
        assert await bl.probe()
        only = asyncio.ensure_future(bl.lookup("1.1.1.1"))
        await asyncio.sleep(0.01)
        only.cancel()
        gate.set()
        for _ in range(5):
            await asyncio.sleep(0)
        return bl

    bl = asyncio.run(go())
    assert calls == ["1.1.1.1"] and not bl._inflight and bl._cache == {"1.1.1.1": True}
